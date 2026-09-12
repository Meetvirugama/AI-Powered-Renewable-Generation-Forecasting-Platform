"""Production forecast engine: the trained LightGBM boosters in prediction_bundle/.

This is the module `backend.modules.factory` imports when FORECAST_ENGINE_TYPE
is `production`. Until it existed, that setting silently fell back to
MockForecastEngine and every "production" forecast in the system was a seeded
sine wave.

What it serves
--------------
`prediction_bundle/models_v2/` -- three boosters (P10/P50/P90) for a 24-hour
horizon over 44 features, retrained by `scripts/train_forecast.py`. Two things
about them shape this module:

* **The target is capacity factor, not MW.** The boosters predict
  AC_POWER / capacity in [0, 1]. A forecast for a specific plant is that
  fraction multiplied by the plant's `avc_mw`. This is what makes one trained
  model usable across four plants of different sizes -- and it is a transfer
  from a reference site, not a per-plant model. Say so when presenting it.
* **The P10-P90 band is conformally calibrated.** Raw quantile regression
  covered 71.5% of held-out observations against a nominal 80%. The manifest
  carries a conformal delta measured on a calibration split the models never
  saw; it is applied here, at inference, because a band that is narrower than
  it claims understates DSM exposure -- the one direction an operator must not
  be misled in.

`prediction_bundle/models_v2/MANIFEST.json` is the contract for both: feature
order, training capacity, the conformal delta, and the measured metrics.

The older `prediction_bundle/models/` bundle is still loadable via
LGBM_MODEL_DIR. It used DC_POWER, DAILY_YIELD and TOTAL_YIELD -- all measured
simultaneously with the target and unavailable for a future block -- and is
rejected by the physics gate below. That rejection is kept as a test, because
it is the evidence for why the retrain was necessary.

Two honesty constraints this module enforces
--------------------------------------------
1. It refuses rather than degrades. If the models are missing, unreadable, or
   the feature frame is too empty to support a meaningful prediction, it raises.
   The factory turns that into a startup failure instead of quietly serving
   mock data.
2. It reports what it did not know. Every result carries a `completeness`
   block naming the features that were NaN, so a weakened forecast is visible
   in the response rather than merely plausible on a chart.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import timezone
from pathlib import Path

import numpy as np

from backend.modules.forecast import feature_builder

logger = logging.getLogger("renewable_platform")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
# models_v2 is the retrained bundle: capacity-factor target, no leaking features,
# conformal-calibrated bands. The original `models/` directory is kept because it
# is what docs/model_integration.md describes, and because the physics gate
# rejecting it is a demonstrable result rather than a deleted mistake.
DEFAULT_MODEL_DIR = PROJECT_ROOT / "prediction_bundle" / "models_v2"
LEGACY_MODEL_DIR = PROJECT_ROOT / "prediction_bundle" / "models"

# Only the 24h horizon is retrained. 48h and 72h fall back to it: a 48-hour lead
# time served by a model trained for 24 is worse than ideal but honest, whereas
# serving the leaking 48h model would not be.
HORIZONS = (24,)
QUANTILE_TAGS = ("P10", "P50", "P90")
MANIFEST_NAME = "MANIFEST.json"

# Below this, a forecast is not worth serving -- too much of the feature space
# is unknown for the boosters to do anything but fall back on their priors.
#
# The number is set against the arithmetic of the feature set, not by feel. Of
# the 44 features, 11 are clock terms that are always computable and 33 come
# from weather. A request with no weather at all therefore lands at exactly
# 25.0%, so the previous threshold of 25 let it through and the engine answered
# from the calendar -- a smooth, plausible, entirely fabricated day. At 75 the
# weather block has to cover roughly two thirds of the day before a forecast is
# served.
MIN_POPULATED_PCT = float(os.getenv("LGBM_MIN_POPULATED_PCT", "75"))


class ModelsUnavailable(RuntimeError):
    """The production models could not be loaded. Never fall back silently."""


class InsufficientFeatures(RuntimeError):
    """Too little of the feature frame is known to produce a usable forecast."""


class PlantCapacityUnknown(RuntimeError):
    """A capacity-factor model was asked to forecast a plant with no `avc_mw`.

    The models predict a fraction of capacity. Without a capacity there is
    nothing to multiply it by, and guessing one would invent the MW figure the
    DSM engine then prices. This is a plants.yaml problem, and it should be
    loud.
    """


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

    # Read by backend.modules.forecast.weather_provider. Declared as an
    # attribute rather than detected with isinstance so a caller can ask the
    # question without importing lightgbm, which the mock path must not pay for.
    requires_weather = True

    def __init__(self, model_directory: Path | None = None) -> None:
        self._dir = Path(model_directory) if model_directory else model_dir()
        self._boosters: dict[str, object] = {}
        self._feature_order: list[str] | None = None
        self._manifest: dict = {}
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
            self._manifest = self._read_manifest(self._feature_order)
            self._boosters = loaded
            logger.info(
                "loaded %d LightGBM boosters from %s (%d features, target=%s)",
                len(loaded), self._dir, len(self._feature_order), self.target,
            )

    def _read_manifest(self, feature_order: list[str]) -> dict:
        """Load MANIFEST.json, and refuse it if it disagrees with the boosters.

        The manifest is where the capacity normalisation and the conformal
        delta live -- numbers that silently change every rupee figure
        downstream. A manifest describing a different model than the one
        actually loaded is worse than no manifest, so a mismatch is fatal
        rather than a warning.
        """
        path = self._dir / MANIFEST_NAME
        if not path.is_file():
            # The legacy bundle predates the manifest. It is served raw, in the
            # units it was trained in, and the physics gate deals with it.
            return {}

        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ModelsUnavailable(f"could not read {path}: {exc}") from exc

        declared = manifest.get("feature_order")
        if declared is not None and list(declared) != feature_order:
            raise ModelsUnavailable(
                f"{MANIFEST_NAME} declares {len(declared)} features in a different "
                f"order than the boosters carry ({len(feature_order)}); refusing to serve"
            )

        if manifest.get("target") == "capacity_factor":
            capacity = manifest.get("training_capacity")
            if not capacity or float(capacity) <= 0:
                raise ModelsUnavailable(
                    f"{MANIFEST_NAME} says the target is capacity_factor but carries no "
                    f"usable training_capacity; the generation lag cannot be rescaled"
                )
        return manifest

    # ----------------------------------------------------- manifest properties
    @property
    def target(self) -> str:
        """`capacity_factor` for models_v2, `AC_POWER` for the legacy bundle."""
        return str(self._manifest.get("target", "AC_POWER"))

    @property
    def predicts_capacity_factor(self) -> bool:
        return self.target == "capacity_factor"

    @property
    def training_capacity(self) -> float:
        """The denominator the capacity factor was computed against, in the
        training data's own units. Only meaningful for a normalised model."""
        return float(self._manifest.get("training_capacity") or 0.0)

    @property
    def conformal_delta(self) -> float:
        """How far P10/P90 are widened, in capacity-factor units.

        Zero when the bundle carries no calibration -- never a guessed default,
        because a made-up widening is indistinguishable from a real one on a
        chart.
        """
        return float((self._manifest.get("conformal") or {}).get("delta_capacity_factor") or 0.0)

    @property
    def feature_order(self) -> list[str]:
        self._load()
        assert self._feature_order is not None
        return self._feature_order

    def health(self) -> dict:
        """Reported by /health so a broken model set is visible before a demo."""
        try:
            self._load()
            metrics = self._manifest.get("metrics") or {}
            return {
                "status": "ok",
                "models_loaded": len(self._boosters),
                "features": len(self.feature_order),
                "model_dir": str(self._dir),
                "target": self.target,
                "horizons_trained": list(HORIZONS),
                "conformal_delta": round(self.conformal_delta, 4) or None,
                # Surfaced so /health states the model's measured quality rather
                # than only that it loaded. A model that loads and forecasts
                # badly looks identical to a good one from the outside.
                "skill_vs_persistence": metrics.get("skill_vs_persistence"),
                "coverage_p10_p90": metrics.get("coverage_p10_p90"),
            }
        except ModelsUnavailable as exc:
            return {"status": "unavailable", "error": str(exc), "model_dir": str(self._dir)}

    # --------------------------------------------------------------- prediction
    @staticmethod
    def _horizon_for(num_blocks: int) -> int:
        """Pick the booster trained nearest the requested lead time.

        Only the 24h horizon was retrained, so longer requests fall back to it.
        A 48-hour lead time served by a 24-hour model is a worse forecast; the
        48h and 72h boosters in the legacy bundle would have been a dishonest
        one, because they were trained on features that do not exist that far
        ahead.
        """
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

    def _rescaled_history(self, history: dict[str, float] | None, avc_mw: float) -> dict:
        """Put the caller's generation lags into the units the model learned.

        `generation_lag_96` is yesterday's generation at the same block. It was
        *not* normalised during training -- only the target was -- so it is in
        the reference plant's raw units. Feeding a 50 MW plant's own history
        straight in would present the model with numbers on a completely
        different scale from anything it saw. Converting through capacity
        factor keeps the feature meaningful across plants, exactly as the
        target normalisation does.
        """
        if not history:
            return {}
        if not self.predicts_capacity_factor or avc_mw <= 0:
            return {k: float(v) for k, v in history.items() if v is not None}

        scale = self.training_capacity / avc_mw
        return {
            name: (float(value) * scale if name.startswith("generation_") else float(value))
            for name, value in history.items()
            if value is not None
        }

    def _dark_blocks(self, frame: np.ndarray, asset_type: str) -> np.ndarray:
        """Blocks where a solar plant physically cannot generate.

        True only where the weather input says shortwave radiation is exactly
        zero -- which Open-Meteo reports before 05:00 and after 19:00 IST at
        this latitude. This is read from the actual input rather than from a
        clock, so a block is never called dark on the strength of an assumption
        about sunrise.

        Wind is exempt: a wind farm at 02:00 is an ordinary operating state.
        """
        if asset_type != "solar" or "shortwave_radiation" not in self.feature_order:
            return np.zeros(frame.shape[0], dtype=bool)

        radiation = frame[:, self.feature_order.index("shortwave_radiation")]
        return ~np.isnan(radiation) & (radiation <= 0.0)

    def _apply_conformal(self, predictions: dict, dark: np.ndarray) -> dict:
        """Widen P10/P90 by the calibrated delta, in capacity-factor space.

        Romano et al. (2019). The delta was measured on a split the boosters
        never trained on, so it corrects the band's *measured* under-coverage
        (71.5% against a nominal 80%) rather than an assumption about it.
        Applied before scaling to MW, so the widening is a property of the
        model rather than of plant size.

        The delta is a single constant across all 96 blocks, which is what makes
        conformal prediction distribution-free -- and also what makes it wrong
        at midnight, where it would lift P90 to ~1.8 MW on a 50 MW solar plant
        that is demonstrably producing nothing. The band is therefore
        intersected with the physical support afterwards. That intersection
        cannot cost coverage: the observation it excludes is a non-zero
        night-time generation, which does not occur.
        """
        if not self.predicts_capacity_factor:
            return predictions

        delta = self.conformal_delta
        widened = {
            "P10": np.clip(predictions["P10"] - delta, 0.0, 1.0),
            "P50": np.clip(predictions["P50"], 0.0, 1.0),
            "P90": np.clip(predictions["P90"] + delta, 0.0, 1.0),
        }
        if dark.any():
            for tag in widened:
                widened[tag] = np.where(dark, 0.0, widened[tag])
        return widened

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

        # plants.yaml and the API use `id`/`type`; the older model code assumed
        # `plant_id`/`asset_type`. Accept both -- reading the wrong key here
        # silently disables the night-time physics check for every solar plant.
        avc_mw = float(plant.get("avc_mw") or 0.0)
        plant_id = plant.get("plant_id") or plant.get("id") or "<unknown>"

        if self.predicts_capacity_factor and avc_mw <= 0:
            raise PlantCapacityUnknown(
                f"plant {plant_id} has no avc_mw, but {self._dir.name} predicts capacity "
                f"factor (a fraction of nameplate). There is nothing to multiply it by. "
                f"Set avc_mw for this plant in config/plants.yaml."
            )

        horizon = self._horizon_for(num_blocks)

        frame = feature_builder.build_frame(
            self.feature_order,
            date_str,
            num_blocks,
            weather=weather,
            history=self._rescaled_history(history, avc_mw),
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
        asset_type = str(plant.get("asset_type") or plant.get("type") or "solar").lower()
        predictions = self._apply_conformal(predictions, self._dark_blocks(frame, asset_type))

        # One number turns the model's output into this plant's MW. For the
        # legacy bundle it is 1.0, because those models predict power directly.
        scale = avc_mw if self.predicts_capacity_factor else 1.0
        scaled = {tag: values * scale for tag, values in predictions.items()}

        model_name = f"lightgbm_{horizon}h"
        timestamps = feature_builder.block_timestamps(date_str, num_blocks)
        blocks: list[dict] = []

        for row in range(num_blocks):
            p10 = float(scaled["P10"][row])
            p50 = float(scaled["P50"][row])
            p90 = float(scaled["P90"][row])

            # Quantile models are fitted independently and can cross, which would
            # render a fan chart with an upper bound below its lower bound.
            p10, p50, p90 = sorted((p10, p50, p90))

            quantiles = self._interpolate_quantiles(p10, p50, p90)

            ordered = sorted(quantiles.items(), key=lambda kv: float(kv[0][1:]))
            running = -float("inf")
            for key, value in ordered:
                value = max(value, 0.0, running)
                if avc_mw > 0:
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

        self._assert_physically_plausible(blocks, plant, scaled)

        logger.info(
            "lgbm forecast plant=%s date=%s blocks=%d horizon=%dh completeness=%.1f%% "
            "peak_p50=%.2f MW",
            plant_id, date_str, num_blocks, horizon, report["populated_pct"],
            float(np.max(scaled["P50"])),
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
        asset_type = str(plant.get("asset_type") or plant.get("type") or "solar").lower()
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
