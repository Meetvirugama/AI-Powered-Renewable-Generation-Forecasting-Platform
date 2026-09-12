"""The production forecast engine, and the guards that stop it fabricating.

These tests encode two things that were wrong before and must not regress:

1. The LightGBM model files load at all. All 12 were unloadable on any Windows
   checkout because `core.autocrlf` rewrote their line endings, and LightGBM
   does not merely fail on that -- it aborts the process.
2. `FORECAST_ENGINE_TYPE=production` either serves real model output or raises.
   It must never quietly hand back the mock, because the DSM engine prices
   whatever it is given into rupee figures that look identical either way.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pytest

from backend.modules.forecast import feature_builder
from backend.modules.forecast.lgbm_model import (
    HORIZONS,
    ImplausibleForecast,
    InsufficientFeatures,
    LGBMForecastEngine,
    ModelsUnavailable,
)

MODEL_DIR = Path(__file__).resolve().parents[1] / "prediction_bundle" / "models"
pytestmark = pytest.mark.skipif(
    not MODEL_DIR.is_dir() or not list(MODEL_DIR.glob("*.txt")),
    reason="prediction_bundle/models not present",
)

PLANT = {"plant_id": "GJ_SOLAR_A", "avc_mw": 50.0, "asset_type": "solar"}


def _weather(num_blocks: int = 96) -> dict[int, dict]:
    """A plausible clear September day, so the frame is populated enough to run."""
    out = {}
    for block in range(1, num_blocks + 1):
        hour = (block - 1) / 4.0
        solar = max(0.0, -((hour - 13.0) ** 2) / 9.0 + 8.0)
        out[block] = {
            "temperature_2m": 26 + 6 * solar / 8,
            "relative_humidity_2m": 70 - 20 * solar / 8,
            "dew_point_2m": 22.0,
            "cloud_cover": 20.0,
            "cloud_cover_low": 10.0,
            "cloud_cover_mid": 5.0,
            "cloud_cover_high": 5.0,
            "shortwave_radiation": 120 * solar,
            "direct_radiation": 95 * solar,
            "diffuse_radiation": 25 * solar,
            "direct_normal_irradiance": 100 * solar,
            "global_tilted_irradiance": 120 * solar,
            "wind_speed_10m": 12.0,
            "wind_direction_10m": 250.0,
            "surface_pressure": 1002.0,
            "precipitation": 0.0,
        }
    return out


# ------------------------------------------------------------------ model files
def test_all_twelve_model_files_are_present():
    assert len(glob.glob(str(MODEL_DIR / "*.txt"))) == 12


def test_model_files_have_no_crlf():
    """The regression guard for the autocrlf corruption.

    .gitattributes marks these binary. If that is ever removed, every Windows
    checkout silently produces models that abort the process on load.
    """
    corrupted = [
        Path(p).name for p in glob.glob(str(MODEL_DIR / "*.txt"))
        if b"\r\n" in Path(p).read_bytes()
    ]
    assert corrupted == [], f"CRLF-corrupted model files: {corrupted}"


def test_every_booster_loads_and_agrees_on_features():
    engine = LGBMForecastEngine()
    health = engine.health()
    assert health["status"] == "ok"
    assert health["models_loaded"] == len(HORIZONS) * 3
    assert health["features"] == 61


def test_feature_order_is_read_from_the_models_not_hardcoded():
    order = LGBMForecastEngine().feature_order
    assert len(order) == 61
    assert order[0] == "PLANT_ID"
    # The three that make a genuine future forecast impossible.
    for name in feature_builder.LEAKING_FEATURES:
        assert name in order


def test_missing_model_directory_raises_rather_than_degrades(tmp_path):
    with pytest.raises(ModelsUnavailable):
        LGBMForecastEngine(model_directory=tmp_path / "nope").feature_order


# --------------------------------------------------------------- feature frame
def test_unknown_features_are_nan_not_zero():
    """NaN means 'unknown' to LightGBM; 0.0 is a claim that the value is zero."""
    order = LGBMForecastEngine().feature_order
    frame = feature_builder.build_frame(order, "2026-09-13", 8)
    for name in feature_builder.LEAKING_FEATURES:
        column = frame[:, order.index(name)]
        assert np.all(np.isnan(column)), f"{name} should be NaN, never imputed"


def test_time_features_are_always_populated():
    order = LGBMForecastEngine().feature_order
    frame = feature_builder.build_frame(order, "2026-09-13", 96)
    for name in ("hour", "hour_sin", "hour_cos", "day_of_year", "is_daytime"):
        assert not np.any(np.isnan(frame[:, order.index(name)])), name


def test_blocks_are_ist_and_quarter_hourly():
    stamps = feature_builder.block_timestamps("2026-09-13", 96)
    assert len(stamps) == 96
    assert stamps[0].hour == 0 and stamps[0].minute == 0
    assert (stamps[1] - stamps[0]).total_seconds() == 900
    assert stamps[-1].hour == 23 and stamps[-1].minute == 45
    assert stamps[0].utcoffset().total_seconds() == 5.5 * 3600


def test_completeness_reports_what_was_missing():
    order = LGBMForecastEngine().feature_order
    frame = feature_builder.build_frame(order, "2026-09-13", 96, weather=_weather())
    report = feature_builder.completeness(order, frame)
    assert 0 < report["populated_pct"] <= 100
    assert set(report["unavailable_by_design"]) == set(feature_builder.LEAKING_FEATURES)


# -------------------------------------------------------------------- refusals
def test_refuses_when_almost_nothing_is_known():
    """No weather supplied: the frame is mostly NaN and the answer would be prior noise."""
    with pytest.raises(InsufficientFeatures) as exc:
        LGBMForecastEngine().generate_forecast(PLANT, "2026-09-13", num_blocks=96)
    assert "feature frame is known" in str(exc.value)


def test_rejects_output_that_violates_physics():
    """The models as trained are on the wrong scale and predict solar at night.

    This is the current, real state of prediction_bundle: the engine must refuse
    rather than let the DSM engine turn it into rupee figures. When the models
    are retrained (see docs/model_integration.md) this test should be revisited
    -- a passing forecast would then be the correct outcome.
    """
    with pytest.raises(ImplausibleForecast) as exc:
        LGBMForecastEngine().generate_forecast(
            PLANT, "2026-09-13", num_blocks=96, weather=_weather()
        )
    message = str(exc.value)
    assert "scale mismatch" in message or "night" in message


def test_the_rejection_explains_what_to_do():
    with pytest.raises(ImplausibleForecast) as exc:
        LGBMForecastEngine().generate_forecast(
            PLANT, "2026-09-13", num_blocks=96, weather=_weather()
        )
    assert "docs/model_integration.md" in str(exc.value)


# -------------------------------------------------------------------- mechanics
def test_horizon_selection_matches_requested_lead_time():
    pick = LGBMForecastEngine._horizon_for
    assert pick(96) == 24     # 24 h
    assert pick(192) == 48    # 48 h
    assert pick(288) == 72    # 72 h


def test_interpolated_quantiles_stay_ordered():
    q = LGBMForecastEngine._interpolate_quantiles(10.0, 20.0, 34.0)
    values = [q[k] for k in ("p05", "p10", "p25", "p50", "p75", "p90", "p95")]
    assert values == sorted(values)
    assert q["p10"] == 10.0 and q["p50"] == 20.0 and q["p90"] == 34.0


def test_degenerate_quantiles_do_not_invert():
    q = LGBMForecastEngine._interpolate_quantiles(5.0, 5.0, 5.0)
    assert len(set(q.values())) == 1


def test_crlf_model_file_is_repaired_in_memory(tmp_path):
    """A checkout made before .gitattributes landed must not abort the process."""
    source = MODEL_DIR / "lightgbm_24h_P50.txt"
    corrupted_dir = tmp_path / "models"
    corrupted_dir.mkdir()
    for name in ("P10", "P50", "P90"):
        for horizon in HORIZONS:
            target = corrupted_dir / f"lightgbm_{horizon}h_{name}.txt"
            target.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))

    engine = LGBMForecastEngine(model_directory=corrupted_dir)
    assert engine.health()["status"] == "ok"
    assert len(engine.feature_order) == 61


def test_model_dir_is_overridable_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LGBM_MODEL_DIR", str(tmp_path))
    from backend.modules.forecast import lgbm_model

    assert lgbm_model.model_dir() == tmp_path


def test_engine_does_not_load_models_at_construction():
    """The factory caches the instance; construction must stay cheap."""
    engine = LGBMForecastEngine(model_directory=Path(os.devnull))
    assert engine._boosters == {}
