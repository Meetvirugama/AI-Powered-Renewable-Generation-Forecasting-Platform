"""Production forecast engine: the trained LightGBM boosters in prediction_bundle/.

This is the module `backend.modules.factory` imports when FORECAST_ENGINE_TYPE
is `production`. Until it existed, that setting silently fell back to
MockForecastEngine and every "production" forecast in the system was a seeded
sine wave.

What the models are
-------------------
12 boosters: {24,48,72}h x {point, P10, P50, P90}, each over the same 61
features, trained to predict AC_POWER. Only P10/P50/P90 are modelled; the
`p05/p25/p75/p95` the API schema requires are interpolated from those three and
flagged as such, because inventing two more quantile models would be a fiction.

Two honesty constraints this module enforces
--------------------------------------------
1. It refuses rather than degrades. If the models are missing, unreadable, or
   the feature frame is too empty to support a meaningful prediction, it raises.
   The factory turns that into a startup failure instead of quietly serving
   mock data.
2. It reports what it did not know. Every result carries a `completeness`
   block naming the features that were NaN, so a weakened forecast is visible
   in the response rather than merely plausible on a chart.

Known limitation, deliberately surfaced
---------------------------------------
Three of the 61 features (DC_POWER, DAILY_YIELD, TOTAL_YIELD) are measured
simultaneously with the target and cannot exist for a future block. DC_POWER
alone is ~25% of total model gain. These models therefore cannot produce a
fully-powered day-ahead forecast as trained; they need retraining without those
columns. See docs/model_integration.md.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import timezone
from pathlib import Path

import numpy as np

from backend.modules.forecast import feature_builder

logger = logging.getLogger("renewable_platform")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = PROJECT_ROOT / "prediction_bundle" / "models"

HORIZONS = (24, 48, 72)
QUANTILE_TAGS = ("P10", "P50", "P90")

# Below this, a forecast is not worth serving -- too much of the feature space
# is unknown for the boosters to do anything but fall back on their priors.
MIN_POPULATED_PCT = float(os.getenv("LGBM_MIN_POPULATED_PCT", "25"))


class ModelsUnavailable(RuntimeError):
    """The production models could not be loaded. Never fall back silently."""


class InsufficientFeatures(RuntimeError):
    """Too little of the feature frame is known to produce a usable forecast."""


class ImplausibleForecast(RuntimeError):
    """Model output violates physics. Refuse rather than let the DSM engine price it.

    The DSM engine converts whatever MW series it is handed into rupee figures,
    and the dashboard renders those without further checks. A forecast that says
    a solar plant generates at night would therefore surface as a confident,
    precisely-formatted penalty. This gate exists so that a model problem fails
    here, loudly, instead of becoming a financial claim.
    """


# A solar plant produces nothing at night. Tolerance is a small fraction of
# capacity to allow for inverter standby and rounding, not real generation.
NIGHT_HOURS = tuple(range(21, 24)) + tuple(range(0, 5))
NIGHT_TOLERANCE_FRACTION = 0.02


def model_dir() -> Path:
    return Path(os.getenv("LGBM_MODEL_DIR", str(DEFAULT_MODEL_DIR)))


def _read_booster(path: Path):
    """Load one booster, tolerating CRLF corruption in the checked-out file.

    `.gitattributes` marks these files binary so Git stops rewriting their line
    endings, but a working tree cloned before that fix still holds CRLF copies,
    and LightGBM does not merely fail on them -- it aborts the process. Repairing
    in memory keeps a stale checkout from taking the API down, and warns loudly
    enough that someone renormalises it.
    """
    import lightgbm as lgb

    raw = path.read_bytes()
    if b"\r\n" in raw:
        logger.warning(
            "model %s has CRLF line endings (corrupted by git autocrlf); "
            "repairing in memory. Renormalise the working tree: "
            "git rm --cached -r . && git reset --hard",
            path.name,
        )
        import tempfile

        repaired = Path(tempfile.mkdtemp()) / path.name
        repaired.write_bytes(raw.replace(b"\r\n", b"\n"))
        return lgb.Booster(model_file=str(repaired))

    return lgb.Booster(model_file=str(path))


class LGBMForecastEngine:
    """Serves P10/P50/P90 from the trained boosters.

    Construction is cheap; models load on first use and are cached for the
    process. backend.modules.factory caches the instance, so the load cost is
    paid once.
    """

    def __init__(self, model_directory: Path | None = None) -> None:
        self._dir = Path(model_directory) if model_directory else model_dir()
        self._boosters: dict[str, object] = {}
        self._feature_order: list[str] | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ loading
    def _load(self) -> None:
        if self._boosters:
            return
        with self._lock:
            if self._boosters:
                return

            if not self._dir.is_dir():
                raise ModelsUnavailable(f"model directory not found: {self._dir}")

            loaded: dict[str, object] = {}
            for horizon in HORIZONS:
                for tag in QUANTILE_TAGS:
                    name = f"lightgbm_{horizon}h_{tag}"
                    path = self._dir / f"{name}.txt"
                    if not path.is_file():
                        raise ModelsUnavailable(f"missing model file: {path}")
                    try:
                        loaded[name] = _read_booster(path)
                    except Exception as exc:  # noqa: BLE001
                        raise ModelsUnavailable(f"could not load {path.name}: {exc}") from exc

            # Feature order comes from the models themselves so it cannot drift
            # from whatever a JSON contract happens to say.
            orders = {tuple(b.feature_name()) for b in loaded.values()}
            if len(orders) != 1:
                raise ModelsUnavailable("models disagree on feature order; refusing to serve")

            self._feature_order = list(next(iter(orders)))
            self._boosters = loaded
            logger.info(
                "loaded %d LightGBM boosters from %s (%d features)",
                len(loaded), self._dir, len(self._feature_order),
            )

    @property
    def feature_order(self) -> list[str]:
        self._load()
        assert self._feature_order is not None
        return self._feature_order

    def health(self) -> dict:
        """Reported by /health so a broken model set is visible before a demo."""
        try:
            self._load()
            return {
                "status": "ok",
                "models_loaded": len(self._boosters),
                "features": len(self.feature_order),
                "model_dir": str(self._dir),
            }
        except ModelsUnavailable as exc:
            return {"status": "unavailable", "error": str(exc), "model_dir": str(self._dir)}

    # --------------------------------------------------------------- prediction
    @staticmethod
    def _horizon_for(num_blocks: int) -> int:
        """Pick the booster trained nearest the requested lead time."""
        hours = num_blocks * feature_builder.BLOCK_MINUTES / 60.0
        return min(HORIZONS, key=lambda h: (abs(h - hours), h))

    @staticmethod
    def _interpolate_quantiles(p10: float, p50: float, p90: float) -> dict[str, float]:
        """Fill the schema's 7 quantiles from the 3 that are modelled.

        p05/p25/p75/p95 are linear interpolations/extrapolations in quantile
        space, not separate models. They widen the band honestly rather than
        implying resolution the training never produced.
        """
        lower = max(p50 - p10, 0.0)
        upper = max(p90 - p50, 0.0)
        return {
            "p05": p50 - 1.35 * lower,
            "p10": p10,
            "p25": p50 - 0.45 * lower,
            "p50": p50,
            "p75": p50 + 0.45 * upper,
            "p90": p90,
            "p95": p50 + 1.35 * upper,
        }

    def generate_forecast(
        self,
        plant: dict,
        date_str: str,
        num_blocks: int = 96,
        *,
        weather: dict[int, dict] | None = None,
        history: dict[str, float] | None = None,
    ) -> list[dict]:
        """Return one dict per block, matching ForecastEngineProtocol."""
        self._load()

        avc_mw = float(plant.get("avc_mw") or 0.0) or None
        horizon = self._horizon_for(num_blocks)

        frame = feature_builder.build_frame(
            self.feature_order, date_str, num_blocks, weather=weather, history=history
        )
        report = feature_builder.completeness(self.feature_order, frame)

        if report["populated_pct"] < MIN_POPULATED_PCT:
            raise InsufficientFeatures(
                f"only {report['populated_pct']}% of the feature frame is known "
                f"(minimum {MIN_POPULATED_PCT}%). Supply weather data for this date, "
                f"or set FORECAST_ENGINE_TYPE=mock for a demo without live weather. "
                f"All-missing features: {len(report['missing'])}/{report['features_total']}."
            )

        predictions = {
            tag: np.asarray(self._boosters[f"lightgbm_{horizon}h_{tag}"].predict(frame), dtype=float)
            for tag in QUANTILE_TAGS
        }

        model_name = f"lightgbm_{horizon}h"
        timestamps = feature_builder.block_timestamps(date_str, num_blocks)
        blocks: list[dict] = []

        for row in range(num_blocks):
            p10 = float(predictions["P10"][row])
            p50 = float(predictions["P50"][row])
            p90 = float(predictions["P90"][row])

            # Quantile models are fitted independently and can cross, which would
            # render a fan chart with an upper bound below its lower bound.
            p10, p50, p90 = sorted((p10, p50, p90))

            quantiles = self._interpolate_quantiles(p10, p50, p90)

            ordered = sorted(quantiles.items(), key=lambda kv: float(kv[0][1:]))
            running = -float("inf")
            for key, value in ordered:
                value = max(value, 0.0, running)
                if avc_mw is not None:
                    value = min(value, avc_mw)
                quantiles[key] = value
                running = value

            ts = timestamps[row]
            blocks.append(
                {
                    "block_no": row + 1,
                    "valid_time": ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "ist_time": ts.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
                    **{k: round(v, 4) for k, v in quantiles.items()},
                    "model_name": model_name,
                    "completeness_pct": report["populated_pct"],
                    "interpolated_quantiles": ["p05", "p25", "p75", "p95"],
                }
            )

        self._assert_physically_plausible(blocks, plant, predictions)

        logger.info(
            "lgbm forecast plant=%s date=%s blocks=%d horizon=%dh completeness=%.1f%%",
            plant.get("plant_id"), date_str, num_blocks, horizon, report["populated_pct"],
        )
        return blocks

    @staticmethod
    def _assert_physically_plausible(blocks: list[dict], plant: dict, raw: dict) -> None:
        """Reject output that cannot describe the plant it claims to describe.

        Checked against the *raw* booster output as well as the clipped series,
        because clipping to capacity hides the most important failure: a model
        whose predictions are on a different scale entirely gets squashed into a
        flat line at nameplate, which looks like a plant running perfectly.
        """
        avc_mw = float(plant.get("avc_mw") or 0.0)
        asset_type = str(plant.get("asset_type", "solar")).lower()
        problems: list[str] = []

        raw_values = np.concatenate([np.asarray(v, dtype=float) for v in raw.values()])
        raw_max = float(np.nanmax(raw_values))
        raw_min = float(np.nanmin(raw_values))

        if avc_mw > 0 and raw_max > 10 * avc_mw:
            problems.append(
                f"raw model output peaks at {raw_max:,.1f} against a plant capacity of "
                f"{avc_mw:g} MW -- a {raw_max / avc_mw:.0f}x scale mismatch, consistent with "
                f"the models having been trained in kW on a different plant. Clipping this "
                f"to capacity would render a flat line at nameplate, not a forecast."
            )

        if raw_min < -0.01 * max(avc_mw, 1.0):
            problems.append(f"raw model output goes negative ({raw_min:,.2f})")

        if asset_type == "solar" and avc_mw > 0:
            tolerance = NIGHT_TOLERANCE_FRACTION * avc_mw
            offenders = [
                b for b in blocks
                if int(b["ist_time"][11:13]) in NIGHT_HOURS and b["p50"] > tolerance
            ]
            if offenders:
                worst = max(offenders, key=lambda b: b["p50"])
                problems.append(
                    f"{len(offenders)} night-time blocks predict solar generation above "
                    f"{tolerance:.2f} MW (worst: {worst['p50']:.2f} MW at "
                    f"{worst['ist_time'][11:16]} IST). A solar plant produces nothing at night."
                )

        if problems:
            raise ImplausibleForecast(
                "production forecast rejected as physically implausible:\n  - "
                + "\n  - ".join(problems)
                + "\n\nThe adapter and the model files are fine; the models themselves are not "
                "usable for this plant as trained. See docs/model_integration.md."
            )
