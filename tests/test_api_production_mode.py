"""Every forecast endpoint, with FORECAST_ENGINE_TYPE=production.

This file exists because the whole suite passed while production mode was
broken. The routes called `generate_forecast()` with no weather; the mock
ignores that argument and the production engine cannot work without it, so the
tests -- which all ran against the mock -- were green while
`FORECAST_ENGINE_TYPE=production` would have returned 500 from `/forecast`,
`/dashboard`, `/dsm`, `/optimize` and `/pooling`.

Open-Meteo is stubbed, so these run offline. What is real is the model: the
actual boosters in `prediction_bundle/models_v2` are loaded and asked for a
forecast, and the physics gate runs on the result.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.modules.forecast import feature_builder, weather_provider

MODEL_DIR = Path(__file__).resolve().parents[1] / "prediction_bundle" / "models_v2"
pytestmark = pytest.mark.skipif(
    not MODEL_DIR.is_dir() or not list(MODEL_DIR.glob("*.txt")),
    reason="prediction_bundle/models_v2 not present",
)

PLANT_ID = "GJ_SOLAR_A"
AVC_MW = 50.0
NIGHT_HOURS = tuple(range(21, 24)) + tuple(range(0, 5))


def _tomorrow() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")


def _clear_sky(date_str: str) -> pd.DataFrame:
    """A clear September day over Gujarat, hourly in UTC.

    Radiation is zero outside 06:00-19:00 IST, which is what Open-Meteo
    actually reports at this latitude. A fixture that claimed otherwise would
    be asking the model about sunlight at midnight, and the night-time physics
    gate would rightly refuse the answer.
    """
    start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(days=1)
    rows = []
    for hour in range(72):
        stamp = start + timedelta(hours=hour)
        ist_hour = (stamp + timedelta(hours=5, minutes=30)).hour
        sun = max(0.0, -((ist_hour - 13.0) ** 2) / 9.0 + 8.0) if 6 <= ist_hour < 19 else 0.0
        rows.append({
            "timestamp": stamp,
            "temperature_2m": 26 + 6 * sun / 8,
            "relative_humidity_2m": 70 - 20 * sun / 8,
            "dew_point_2m": 22.0,
            "cloud_cover": 20.0,
            "cloud_cover_low": 10.0,
            "cloud_cover_mid": 5.0,
            "cloud_cover_high": 5.0,
            "shortwave_radiation": 120 * sun,
            "direct_radiation": 95 * sun,
            "diffuse_radiation": 25 * sun,
            "direct_normal_irradiance": 100 * sun,
            "global_tilted_irradiance": 120 * sun,
            "wind_speed_10m": 12.0,
            "wind_direction_10m": 250.0,
            "surface_pressure": 1002.0,
            "precipitation": 0.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "production")
    monkeypatch.setattr(
        weather_provider, "_fetch", lambda lat, lon: _clear_sky(_tomorrow())
    )
    weather_provider.clear_cache()

    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client
    weather_provider.clear_cache()


# --------------------------------------------------------------------- health
def test_health_does_not_list_the_forecast_as_synthetic(client):
    body = client.get("/health").json()
    assert body["engines"]["forecast"] == "production"
    assert "forecast" not in body.get("serving_synthetic_data", [])


def test_health_carries_the_models_measured_quality(client):
    models = client.get("/health").json()["forecast_models"]
    assert models["status"] == "ok"
    assert models["target"] == "capacity_factor"
    assert models["skill_vs_persistence"] > 0


# ------------------------------------------------------------------- forecast
def test_forecast_endpoint_serves_the_real_model(client):
    body = client.get(f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}").json()
    assert body["model_name"] == "lightgbm_24h", "a real forecast must not be labelled mock"
    assert len(body["blocks"]) == 96


def test_forecast_is_plant_scale_megawatts(client):
    """Capacity factor served as MW would be a number between 0 and 1, priced
    by the DSM engine into penalties ~50x too small with nothing looking wrong."""
    blocks = client.get(f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}").json()["blocks"]
    peak = max(b["p50"] for b in blocks)
    assert 5.0 < peak <= AVC_MW


def test_forecast_is_zero_at_night(client):
    blocks = client.get(f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}").json()["blocks"]
    night = [b for b in blocks if int(b["ist_time"][11:13]) in NIGHT_HOURS]
    assert night and max(b["p95"] for b in night) == 0.0


def test_forecast_quantiles_never_invert(client):
    blocks = client.get(f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}").json()["blocks"]
    keys = ("p05", "p10", "p25", "p50", "p75", "p90", "p95")
    for block in blocks:
        values = [block[k] for k in keys]
        assert values == sorted(values), f"inverted at block {block['block_no']}"


# ------------------------------------------------------- the rest of the chain
def test_dashboard_prices_the_real_forecast(client):
    body = client.get(f"/dashboard/{PLANT_ID}?date={_tomorrow()}").json()
    assert body["forecast"]["model_name"] == "lightgbm_24h"
    assert body["dsm_summary"]["total_expected_penalty_inr"] > 0
    assert body["dsm_summary"]["rule_version"]


def test_dsm_endpoint_accepts_a_schedule_built_from_the_real_forecast(client):
    date_str = _tomorrow()
    blocks = client.get(f"/forecast?plant_id={PLANT_ID}&date={date_str}").json()["blocks"]
    schedule = [b["p50"] for b in blocks]
    response = client.post(
        "/dsm", json={"plant_id": PLANT_ID, "date": date_str, "schedule_mw": schedule}
    )
    assert response.status_code == 200
    assert len(response.json()["blocks"]) == 96


def test_optimize_endpoint_runs_on_the_real_forecast(client):
    response = client.post(
        "/optimize", json={"plant_id": PLANT_ID, "date": _tomorrow(), "avc_mw": AVC_MW}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["naive_total_inr"] >= body["optimised_total_inr"]
    assert len(body["optimised_schedule"]) == 96


def test_pooling_endpoint_runs_on_the_real_forecast(client):
    response = client.post("/pooling", json={"pool_id": "GJ_POOL_1", "date": _tomorrow()})
    assert response.status_code == 200
    body = response.json()
    assert body["individual_total_inr"] >= body["pooled_total_inr"]


# ---------------------------------------------------------------- degradation
def test_the_api_refuses_rather_than_inventing_a_day_when_weather_is_gone(
    client, monkeypatch
):
    """Open-Meteo being unreachable must produce an error, not a smooth
    plausible forecast derived from the calendar. Of 44 features, 11 are clock
    terms that are always computable -- enough to draw a convincing curve."""
    monkeypatch.setattr(weather_provider, "_fetch", lambda lat, lon: pd.DataFrame())
    weather_provider.clear_cache()

    with pytest.raises(Exception) as exc:
        client.get(f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}")
    assert "feature frame is known" in str(exc.value)


def test_weather_is_fetched_once_for_a_dashboard_load(client, monkeypatch):
    """The dashboard route forecasts the plant and then every other plant in
    its pool. Without the cache that is a separate Open-Meteo round trip per
    plant per endpoint."""
    calls: list[tuple[float, float]] = []

    def counted(lat, lon):
        calls.append((lat, lon))
        return _clear_sky(_tomorrow())

    monkeypatch.setattr(weather_provider, "_fetch", counted)
    weather_provider.clear_cache()

    client.get(f"/dashboard/{PLANT_ID}?date={_tomorrow()}")
    assert len(calls) == len(set(calls)), "the same plant's weather was fetched twice"


def test_the_feature_builder_and_the_ingester_agree_on_the_variable_list():
    """The frame is built from WEATHER_FEATURES; anything the ingester does not
    request arrives as NaN and is silently replaced by a learned default."""
    from backend.data.ingestion.openmeteo import HOURLY_VARIABLES

    assert set(feature_builder.WEATHER_FEATURES) <= set(HOURLY_VARIABLES)


# ------------------------------------------------------------------- horizons
@pytest.mark.parametrize("hours,blocks,model", [(24, 96, "lightgbm_24h"),
                                                (48, 192, "lightgbm_48h"),
                                                (72, 288, "lightgbm_72h")])
def test_each_horizon_is_served_by_its_own_model(client, hours, blocks, model):
    """The brief asks for 24-72 hours and three horizons are trained, but the
    route took no horizon argument -- so every call used the default 96 blocks
    and the 48h and 72h boosters sat in memory, advertised by /health as
    `horizons_trained`, and were never reachable."""
    body = client.get(f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}&hours={hours}").json()
    assert len(body["blocks"]) == blocks
    assert body["model_name"] == model


def test_a_longer_horizon_gets_its_own_weather_not_the_shorter_one_cached(client):
    """Regression: the weather cache keyed on (plant, date) and not on the
    number of blocks. A 24-hour request cached 96 blocks, a 48-hour request for
    the same plant and date was handed that same dict, half the frame arrived
    empty, completeness fell to 62.6% and the engine refused a horizon it can
    serve perfectly well."""
    client.get(f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}&hours=24")
    response = client.get(f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}&hours=48")
    assert response.status_code == 200
    assert len(response.json()["blocks"]) == 192


def test_a_72_hour_forecast_spans_three_calendar_days(client):
    blocks = client.get(
        f"/forecast?plant_id={PLANT_ID}&date={_tomorrow()}&hours=72"
    ).json()["blocks"]
    days = {b["ist_time"][:10] for b in blocks}
    assert len(days) == 3


def test_an_unsupported_horizon_is_refused_rather_than_rounded(client):
    """Silently serving 24 hours to a caller who asked for 36 would be
    indistinguishable from a working long-range forecast; the response carries
    no horizon field to contradict it."""
    response = client.get(f"/forecast?plant_id={PLANT_ID}&hours=36")
    assert response.status_code == 422
    assert "24, 48, 72" in str(response.json()["detail"])


def test_health_only_advertises_horizons_the_api_can_actually_serve(client):
    """/health listed [24, 48, 72] while the route could only produce 24."""
    from backend.api.forecast import SUPPORTED_HOURS

    advertised = client.get("/health").json()["forecast_models"]["horizons_trained"]
    assert sorted(advertised) == sorted(SUPPORTED_HOURS)
