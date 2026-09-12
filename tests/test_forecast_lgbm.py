"""The production forecast engine, and the guards that stop it fabricating.

These tests encode what was wrong before and must not regress:

1. The LightGBM model files load at all. All 12 of the original models were
   unloadable on any Windows checkout because `core.autocrlf` rewrote their
   line endings, and LightGBM does not merely fail on that -- it aborts the
   process.
2. `FORECAST_ENGINE_TYPE=production` either serves real model output or raises.
   It must never quietly hand back the mock, because the DSM engine prices
   whatever it is given into rupee figures that look identical either way.
3. The retrained bundle is served in the plant's own MW. The boosters predict a
   capacity factor; forgetting to multiply by `avc_mw` would send a number
   between 0 and 1 into the DSM engine and produce penalties three orders of
   magnitude too small, with nothing about the response looking wrong.
4. The band that reaches the optimiser is the conformally widened one. The raw
   quantile models cover 71.5% of observations against a nominal 80%, and a
   band narrower than it claims makes the optimiser under-hedge.

The legacy bundle in `prediction_bundle/models/` is kept and still tested: it
is the evidence for why the retrain was necessary, and the physics gate must go
on rejecting it.
"""
from __future__ import annotations

import glob
import json
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
    PlantCapacityUnknown,
)

BUNDLE = Path(__file__).resolve().parents[1] / "prediction_bundle"
MODEL_DIR = BUNDLE / "models_v2"
LEGACY_DIR = BUNDLE / "models"

pytestmark = pytest.mark.skipif(
    not MODEL_DIR.is_dir() or not list(MODEL_DIR.glob("*.txt")),
    reason="prediction_bundle/models_v2 not present",
)

PLANT = {"id": "GJ_SOLAR_A", "avc_mw": 50.0, "type": "solar"}
WIND = {"id": "GJ_WIND_C", "avc_mw": 40.0, "type": "wind"}
SMALL_SOLAR = {"id": "GJ_SOLAR_D", "avc_mw": 30.0, "type": "solar"}

NIGHT_HOURS = tuple(range(21, 24)) + tuple(range(0, 5))


def _weather(num_blocks: int = 96) -> dict[int, dict]:
    """A plausible clear September day in Gujarat.

    Radiation is zero outside 06:00-19:00 IST because that is what Open-Meteo
    actually reports at this latitude -- the training data has exactly 0 W/m2
    before 05:00 and after 19:00. A fixture claiming otherwise would ask the
    model a question it never saw, and the night-time physics gate would
    correctly refuse the answer.
    """
    out = {}
    for block in range(1, num_blocks + 1):
        hour = ((block - 1) / 4.0) % 24
        solar = max(0.0, -((hour - 13.0) ** 2) / 9.0 + 8.0) if 6.0 <= hour < 19.0 else 0.0
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


@pytest.fixture(scope="module")
def engine() -> LGBMForecastEngine:
    return LGBMForecastEngine()


@pytest.fixture(scope="module")
def forecast(engine) -> list[dict]:
    return engine.generate_forecast(PLANT, "2026-09-13", 96, weather=_weather())


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((MODEL_DIR / "MANIFEST.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ model files
def test_the_retrained_bundle_is_complete():
    for tag in ("P10", "P50", "P90"):
        assert (MODEL_DIR / f"lightgbm_24h_{tag}.txt").is_file()
    assert (MODEL_DIR / "MANIFEST.json").is_file()


def test_no_model_file_has_crlf():
    """The regression guard for the autocrlf corruption.

    .gitattributes marks these binary. If that is ever removed, every Windows
    checkout silently produces models that abort the process on load.
    """
    paths = glob.glob(str(MODEL_DIR / "*.txt")) + glob.glob(str(LEGACY_DIR / "*.txt"))
    corrupted = [Path(p).name for p in paths if b"\r\n" in Path(p).read_bytes()]
    assert corrupted == [], f"CRLF-corrupted model files: {corrupted}"


def test_every_booster_loads_and_agrees_on_features(engine):
    health = engine.health()
    assert health["status"] == "ok"
    assert health["models_loaded"] == len(HORIZONS) * 3
    assert health["features"] == 44
    assert health["target"] == "capacity_factor"


def test_health_reports_measured_quality_not_just_that_it_loaded(engine):
    """A model that loads and forecasts badly looks identical from outside."""
    health = engine.health()
    assert health["skill_vs_persistence"] > 0
    assert 0.75 <= health["coverage_p10_p90"] <= 0.95
    assert health["conformal_delta"] > 0


def test_feature_order_is_read_from_the_models_not_hardcoded(engine, manifest):
    order = engine.feature_order
    assert order == manifest["feature_order"]
    assert len(order) == 44


def test_no_leaking_feature_survived_the_retrain(engine):
    """DC_POWER and friends are measured with the target; they cannot exist
    for a future block, and their presence is what made the old models
    unusable day-ahead."""
    for name in feature_builder.LEAKING_FEATURES:
        assert name not in engine.feature_order


def test_no_lag_shorter_than_the_horizon_survived(engine):
    """A 24h-ahead forecast cannot see generation from 1 block ago."""
    lags = [f for f in engine.feature_order if f.startswith("generation_lag_")]
    assert lags == ["generation_lag_96"]  # 96 blocks = exactly 24 h


def test_missing_model_directory_raises_rather_than_degrades(tmp_path):
    with pytest.raises(ModelsUnavailable):
        LGBMForecastEngine(model_directory=tmp_path / "nope").feature_order


def test_a_manifest_that_disagrees_with_the_boosters_is_fatal(tmp_path):
    """A manifest describing a different model is worse than no manifest --
    it carries the capacity and the conformal delta, and both silently change
    every rupee figure downstream."""
    models = tmp_path / "models"
    models.mkdir()
    for tag in ("P10", "P50", "P90"):
        (models / f"lightgbm_24h_{tag}.txt").write_bytes(
            (MODEL_DIR / f"lightgbm_24h_{tag}.txt").read_bytes()
        )
    (models / "MANIFEST.json").write_text(
        json.dumps({"target": "capacity_factor", "feature_order": ["nope"],
                    "training_capacity": 1.0}),
        encoding="utf-8",
    )
    with pytest.raises(ModelsUnavailable) as exc:
        LGBMForecastEngine(model_directory=models).feature_order
    assert "different" in str(exc.value)


# --------------------------------------------------------------- feature frame
def test_time_features_are_always_populated(engine):
    order = engine.feature_order
    frame = feature_builder.build_frame(order, "2026-09-13", 96)
    for name in ("hour", "hour_sin", "hour_cos", "day_of_year", "is_daytime"):
        assert not np.any(np.isnan(frame[:, order.index(name)])), name


def test_unknown_features_are_nan_not_zero(engine):
    """NaN means 'unknown' to LightGBM; 0.0 is a claim that the value is zero.

    `generation_lag_96` has no source at serving time -- nothing in the
    pipeline passes yesterday's actuals yet -- so it must arrive as NaN and let
    the boosters use their learned default direction.
    """
    order = engine.feature_order
    frame = feature_builder.build_frame(order, "2026-09-13", 8, weather=_weather(8))
    column = frame[:, order.index("generation_lag_96")]
    assert np.all(np.isnan(column))


def test_blocks_are_ist_and_quarter_hourly():
    stamps = feature_builder.block_timestamps("2026-09-13", 96)
    assert len(stamps) == 96
    assert stamps[0].hour == 0 and stamps[0].minute == 0
    assert (stamps[1] - stamps[0]).total_seconds() == 900
    assert stamps[-1].hour == 23 and stamps[-1].minute == 45
    assert stamps[0].utcoffset().total_seconds() == 5.5 * 3600


def test_completeness_reports_what_was_missing(engine):
    order = engine.feature_order
    frame = feature_builder.build_frame(order, "2026-09-13", 96, weather=_weather())
    report = feature_builder.completeness(order, frame)
    assert 90 <= report["populated_pct"] <= 100


# ------------------------------------------------------- a real served forecast
def test_a_full_day_is_served(forecast):
    assert len(forecast) == 96
    assert forecast[0]["block_no"] == 1
    assert forecast[0]["ist_time"][11:16] == "00:00"
    assert forecast[-1]["ist_time"][11:16] == "23:45"
    assert forecast[0]["model_name"] == "lightgbm_24h"


def test_output_is_in_megawatts_not_capacity_factor(forecast):
    """The single most dangerous scaling bug in the chain.

    A capacity factor served as MW is between 0 and 1, which the DSM engine
    would price into penalties ~50x too small while every field in the response
    still looked well-formed.
    """
    peak = max(b["p50"] for b in forecast)
    assert 10.0 < peak <= PLANT["avc_mw"], f"peak p50 {peak} MW is not a plant-scale number"


def test_the_same_model_scales_to_a_differently_sized_plant(engine):
    """Capacity-factor transfer is the whole reason one model serves four
    plants. The shape must be identical and the magnitude proportional."""
    big = engine.generate_forecast(PLANT, "2026-09-13", 96, weather=_weather())
    small = engine.generate_forecast(SMALL_SOLAR, "2026-09-13", 96, weather=_weather())
    ratio = SMALL_SOLAR["avc_mw"] / PLANT["avc_mw"]
    for a, b in zip(big, small):
        assert b["p50"] == pytest.approx(a["p50"] * ratio, abs=1e-3)


def test_nothing_exceeds_nameplate(forecast):
    assert all(b["p95"] <= PLANT["avc_mw"] + 1e-9 for b in forecast)


def test_nothing_is_negative(forecast):
    assert all(b["p05"] >= 0.0 for b in forecast)


def test_quantiles_never_invert(forecast):
    keys = ("p05", "p10", "p25", "p50", "p75", "p90", "p95")
    for block in forecast:
        values = [block[k] for k in keys]
        assert values == sorted(values), f"inverted at block {block['block_no']}"


def test_a_solar_plant_generates_nothing_at_night(forecast):
    """Including the upper bound. The conformal delta is one constant across
    all 96 blocks, so without the physical-support intersection it would lift
    P90 to ~1.8 MW at midnight on a plant that is demonstrably producing
    nothing -- and the DSM engine would price that."""
    night = [b for b in forecast if int(b["ist_time"][11:13]) in NIGHT_HOURS]
    assert night
    assert max(b["p95"] for b in night) == 0.0


def test_the_band_is_the_conformally_widened_one(engine):
    """Compare the served band against the raw boosters. If the widening were
    ever dropped, the band would silently narrow and the optimiser would
    under-hedge -- the one direction an operator must not be misled in.
    """
    weather = _weather()
    served = engine.generate_forecast(PLANT, "2026-09-13", 96, weather=weather)
    frame = feature_builder.build_frame(engine.feature_order, "2026-09-13", 96, weather=weather)

    raw_p10 = engine._boosters["lightgbm_24h_P10"].predict(frame)
    raw_p90 = engine._boosters["lightgbm_24h_P90"].predict(frame)
    delta = engine.conformal_delta

    daylight = [
        i for i, b in enumerate(served)
        if 8 <= int(b["ist_time"][11:13]) <= 16
    ]
    assert daylight
    for i in daylight:
        expected_p10 = max(0.0, (raw_p10[i] - delta)) * PLANT["avc_mw"]
        expected_p90 = min(1.0, (raw_p90[i] + delta)) * PLANT["avc_mw"]
        assert served[i]["p10"] == pytest.approx(expected_p10, abs=1e-3)
        assert served[i]["p90"] == pytest.approx(expected_p90, abs=1e-3)


def test_widening_is_a_property_of_the_model_not_of_plant_size(engine):
    """Applied in capacity-factor space, so the band is the same fraction of
    nameplate on a 50 MW plant and a 30 MW one."""
    big = engine.generate_forecast(PLANT, "2026-09-13", 96, weather=_weather())
    small = engine.generate_forecast(SMALL_SOLAR, "2026-09-13", 96, weather=_weather())
    ratio = SMALL_SOLAR["avc_mw"] / PLANT["avc_mw"]
    for a, b in zip(big, small):
        assert (b["p90"] - b["p10"]) == pytest.approx(
            (a["p90"] - a["p10"]) * ratio, abs=1e-3
        )


def test_a_wind_farm_is_not_zeroed_at_night(engine):
    """The night-time clamp is a fact about sunlight, not about the clock.
    Applying it to wind would erase real overnight generation -- and with it
    the overnight DSM exposure the platform exists to price."""
    wind = engine.generate_forecast(WIND, "2026-09-13", 96, weather=_weather())
    night = [b for b in wind if int(b["ist_time"][11:13]) in NIGHT_HOURS]
    assert max(b["p90"] for b in night) > 0.0


def test_the_response_says_which_quantiles_were_interpolated(forecast):
    """Only P10/P50/P90 are modelled. Presenting p05/p25/p75/p95 without
    saying so would imply four models that do not exist."""
    assert forecast[0]["interpolated_quantiles"] == ["p05", "p25", "p75", "p95"]


# -------------------------------------------------------------------- refusals
def test_refuses_when_almost_nothing_is_known(engine):
    """No weather supplied: the frame is mostly NaN and the answer would be
    prior noise dressed as a forecast.

    Worth a specific guard. Of 44 features, exactly 11 are clock terms that are
    always computable, so a weatherless request sits at precisely 25.0% -- and
    the threshold inherited from the 61-feature models was 25, which let it
    through. The engine would have served a smooth, plausible day derived
    entirely from the calendar.
    """
    with pytest.raises(InsufficientFeatures) as exc:
        engine.generate_forecast(PLANT, "2026-09-13", num_blocks=96)
    assert "feature frame is known" in str(exc.value)


def test_a_clock_only_frame_sits_at_exactly_25_percent(engine):
    """The arithmetic the threshold is set against; if the feature set changes,
    this is what should fail first."""
    frame = feature_builder.build_frame(engine.feature_order, "2026-09-13", 96)
    report = feature_builder.completeness(engine.feature_order, frame)
    assert report["populated_pct"] == pytest.approx(25.0, abs=0.1)


def test_half_a_day_of_missing_weather_is_refused(engine):
    """A partial Open-Meteo response is the realistic failure, not an empty one."""
    partial = {b: v for b, v in _weather().items() if b <= 40}
    with pytest.raises(InsufficientFeatures):
        engine.generate_forecast(PLANT, "2026-09-13", 96, weather=partial)


def test_refuses_a_plant_with_no_capacity(engine):
    """The models predict a fraction of nameplate. With no nameplate there is
    nothing to multiply it by, and a default would invent the MW figure."""
    with pytest.raises(PlantCapacityUnknown) as exc:
        engine.generate_forecast(
            {"id": "GJ_MYSTERY", "type": "solar"}, "2026-09-13", 96, weather=_weather()
        )
    assert "avc_mw" in str(exc.value)


@pytest.mark.skipif(not LEGACY_DIR.is_dir(), reason="legacy bundle not present")
def test_the_legacy_models_are_still_rejected_by_the_physics_gate():
    """This is the evidence for why the retrain happened.

    Those 12 boosters were trained in kW on a different plant and used three
    features measured simultaneously with the target. Served against a 50 MW
    plant they predict a scale-mismatched series, and the gate must refuse it
    rather than let the DSM engine turn it into rupee figures.
    """
    engine = LGBMForecastEngine(model_directory=LEGACY_DIR)
    with pytest.raises((ImplausibleForecast, InsufficientFeatures)) as exc:
        engine.generate_forecast(PLANT, "2026-09-13", 96, weather=_weather())
    message = str(exc.value)
    assert "scale mismatch" in message or "night" in message or "feature frame" in message


# -------------------------------------------------------------------- mechanics
def test_longer_lead_times_fall_back_to_the_only_retrained_horizon():
    """Only 24h was retrained. A 48h request gets the 24h model, which is a
    worse forecast; the legacy 48h model would have been a dishonest one."""
    pick = LGBMForecastEngine._horizon_for
    assert pick(96) == 24
    assert pick(192) == 24
    assert pick(288) == 24


def test_interpolated_quantiles_stay_ordered():
    q = LGBMForecastEngine._interpolate_quantiles(10.0, 20.0, 34.0)
    values = [q[k] for k in ("p05", "p10", "p25", "p50", "p75", "p90", "p95")]
    assert values == sorted(values)
    assert q["p10"] == 10.0 and q["p50"] == 20.0 and q["p90"] == 34.0


def test_degenerate_quantiles_do_not_invert():
    q = LGBMForecastEngine._interpolate_quantiles(5.0, 5.0, 5.0)
    assert len(set(q.values())) == 1


def test_generation_history_is_rescaled_into_the_units_the_model_learned(engine):
    """`generation_lag_96` was never normalised during training -- only the
    target was. Feeding a 50 MW plant's own history straight in would present
    numbers on a completely different scale from anything the model saw."""
    rescaled = engine._rescaled_history({"generation_lag_96": 25.0}, avc_mw=50.0)
    assert rescaled["generation_lag_96"] == pytest.approx(
        25.0 / 50.0 * engine.training_capacity
    )


def test_history_rescaling_leaves_non_generation_features_alone(engine):
    rescaled = engine._rescaled_history(
        {"generation_lag_96": 25.0, "cloud_cover": 40.0}, avc_mw=50.0
    )
    assert rescaled["cloud_cover"] == 40.0


def test_crlf_model_file_is_repaired_in_memory(tmp_path):
    """A checkout made before .gitattributes landed must not abort the process."""
    corrupted_dir = tmp_path / "models"
    corrupted_dir.mkdir()
    for tag in ("P10", "P50", "P90"):
        source = MODEL_DIR / f"lightgbm_24h_{tag}.txt"
        (corrupted_dir / source.name).write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    (corrupted_dir / "MANIFEST.json").write_bytes((MODEL_DIR / "MANIFEST.json").read_bytes())

    engine = LGBMForecastEngine(model_directory=corrupted_dir)
    assert engine.health()["status"] == "ok"
    assert len(engine.feature_order) == 44


def test_model_dir_is_overridable_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LGBM_MODEL_DIR", str(tmp_path))
    from backend.modules.forecast import lgbm_model

    assert lgbm_model.model_dir() == tmp_path


def test_engine_does_not_load_models_at_construction():
    """The factory caches the instance; construction must stay cheap."""
    engine = LGBMForecastEngine(model_directory=Path(os.devnull))
    assert engine._boosters == {}
