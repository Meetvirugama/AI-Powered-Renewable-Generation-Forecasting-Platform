"""Weather supplied to the production forecast engine.

The engine needs 33 weather features and refuses without them, but every API
route used to call it with none -- so `FORECAST_ENGINE_TYPE=production` would
have returned 500 from all six forecast endpoints while the mock returned a
plausible chart. These tests cover the seam that fixed that, and the two ways
it could go quietly wrong: serving invented weather on failure, or fetching
weather the engine will not use.

No test here touches the network. Open-Meteo responses are constructed
in-process.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backend.modules.forecast import feature_builder, weather_provider
from backend.modules.forecast.weather_provider import (
    _to_blocks,
    clear_cache,
    forecast_for,
    weather_for,
)

PLANT = {"id": "GJ_SOLAR_A", "type": "solar", "avc_mw": 50.0, "lat": 23.2156, "lon": 72.6369}


def _tomorrow() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")


def _hourly_response(date_str: str, hours: int = 72) -> pd.DataFrame:
    """What `fetch_weather_forecast` returns: hourly UTC rows, one column per
    requested variable."""
    start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(days=1)
    stamps = [start + timedelta(hours=h) for h in range(hours)]
    data = {"timestamp": stamps}
    for name in feature_builder.WEATHER_FEATURES:
        data[name] = [float(h % 24) for h in range(hours)]
    return pd.DataFrame(data)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


# ------------------------------------------------------------------ resampling
def test_hourly_data_becomes_96_quarter_hourly_blocks():
    date_str = _tomorrow()
    blocks = _to_blocks(_hourly_response(date_str), date_str, 96)
    assert sorted(blocks) == list(range(1, 97))


def test_every_model_weather_feature_is_carried_through():
    date_str = _tomorrow()
    blocks = _to_blocks(_hourly_response(date_str), date_str, 96)
    assert set(blocks[1]) == set(feature_builder.WEATHER_FEATURES)


def test_blocks_are_interpolated_not_held_flat():
    """Holding each hourly reading across four blocks would put a visible
    staircase in the forecast; irradiance does not move in steps."""
    date_str = _tomorrow()
    blocks = _to_blocks(_hourly_response(date_str), date_str, 96)
    within_one_hour = [blocks[b]["shortwave_radiation"] for b in (41, 42, 43, 44)]
    assert len(set(within_one_hour)) > 1


def test_block_1_is_midnight_ist_not_midnight_utc():
    """A settlement day starts at 00:00 IST. Matching on UTC date strings would
    shift the whole series by 22 blocks."""
    date_str = _tomorrow()
    blocks = _to_blocks(_hourly_response(date_str), date_str, 96)
    expected = feature_builder.block_timestamps(date_str, 96)[0]
    assert expected.hour == 0 and expected.minute == 0
    assert expected.utcoffset().total_seconds() == 5.5 * 3600
    assert blocks[1]  # the instant exists in the resampled frame


def test_an_empty_response_yields_no_blocks_rather_than_zeros():
    """Zero irradiance is a claim about the sky. Absent data must stay absent,
    so the engine can refuse instead of forecasting a permanently dark day."""
    assert _to_blocks(pd.DataFrame(), _tomorrow(), 96) == {}
    assert _to_blocks(None, _tomorrow(), 96) == {}


# -------------------------------------------------------------------- fetching
def test_a_plant_without_coordinates_gets_no_weather():
    assert weather_for({"id": "GJ_MYSTERY", "type": "solar"}, _tomorrow()) == {}


def test_a_failed_fetch_returns_empty_rather_than_raising(monkeypatch):
    """An exception here would surface as an opaque 500 on a dashboard load.
    An empty result surfaces as the engine's explicit refusal instead."""
    def boom(*args, **kwargs):
        raise RuntimeError("open-meteo is down")

    monkeypatch.setattr(weather_provider, "_fetch", boom)
    assert weather_for(PLANT, _tomorrow()) == {}


def test_a_date_outside_the_forecast_window_is_not_requested(monkeypatch):
    """Open-Meteo's free endpoint holds only a few days of past data; asking it
    for last month returns nothing and costs a round trip."""
    called = []
    monkeypatch.setattr(weather_provider, "_fetch", lambda lat, lon: called.append(1))
    assert weather_for(PLANT, "2020-01-15") == {}
    assert called == []


def test_a_malformed_date_is_treated_as_out_of_window(monkeypatch):
    monkeypatch.setattr(weather_provider, "_fetch", lambda lat, lon: pytest.fail("fetched"))
    assert weather_for(PLANT, "not-a-date") == {}


def test_a_second_request_for_the_same_plant_and_date_is_served_from_cache(monkeypatch):
    """A dashboard load fans out across several endpoints for one plant."""
    date_str = _tomorrow()
    calls = []

    def fetch(lat, lon):
        calls.append(1)
        return _hourly_response(date_str)

    monkeypatch.setattr(weather_provider, "_fetch", fetch)
    first = weather_for(PLANT, date_str)
    second = weather_for(PLANT, date_str)
    assert first and first == second
    assert len(calls) == 1


def test_a_failed_fetch_is_not_cached(monkeypatch):
    """Caching a failure would keep the API refusing for the full TTL after
    Open-Meteo recovered."""
    date_str = _tomorrow()
    monkeypatch.setattr(weather_provider, "_fetch", lambda lat, lon: pd.DataFrame())
    assert weather_for(PLANT, date_str) == {}

    monkeypatch.setattr(weather_provider, "_fetch", lambda lat, lon: _hourly_response(date_str))
    assert weather_for(PLANT, date_str)


def test_different_plants_do_not_share_a_cache_entry(monkeypatch):
    """They sit up to 400 km apart; one plant's sky is not another's."""
    date_str = _tomorrow()
    monkeypatch.setattr(weather_provider, "_fetch", lambda lat, lon: _hourly_response(date_str))
    weather_for(PLANT, date_str)
    other = dict(PLANT, id="GJ_WIND_C", lat=23.6102, lon=68.9761)

    calls = []

    def fetch(lat, lon):
        calls.append(1)
        return _hourly_response(date_str)

    monkeypatch.setattr(weather_provider, "_fetch", fetch)
    weather_for(other, date_str)
    assert len(calls) == 1


# ----------------------------------------------------------------- the seam
class _Recorder:
    """Stands in for a forecast engine and remembers how it was called."""

    def __init__(self, requires_weather: bool):
        self.requires_weather = requires_weather
        self.kwargs = None

    def generate_forecast(self, **kwargs):
        self.kwargs = kwargs
        return [{"block_no": 1}]


def test_the_mock_engine_is_not_charged_a_network_round_trip(monkeypatch):
    """The mock invents its series from a seeded RNG; fetching real weather for
    it would be a call whose result is discarded."""
    monkeypatch.setattr(weather_provider, "weather_for", lambda *a, **k: pytest.fail("fetched"))
    engine = _Recorder(requires_weather=False)
    forecast_for(engine, PLANT, _tomorrow())
    assert "weather" not in engine.kwargs


def test_the_production_engine_is_given_weather(monkeypatch):
    monkeypatch.setattr(weather_provider, "weather_for", lambda *a, **k: {1: {"cloud_cover": 5.0}})
    engine = _Recorder(requires_weather=True)
    forecast_for(engine, PLANT, _tomorrow())
    assert engine.kwargs["weather"] == {1: {"cloud_cover": 5.0}}


def test_an_engine_that_declares_nothing_is_treated_as_not_needing_weather():
    """Back-compatible with any engine written before the attribute existed."""
    class Bare:
        def generate_forecast(self, **kwargs):
            return [kwargs]

    assert "weather" not in Bare().generate_forecast(plant=PLANT, date_str="x")[0]
    result = forecast_for(Bare(), PLANT, _tomorrow())
    assert "weather" not in result[0]


def test_the_real_engines_declare_what_they_need():
    """The attribute is the contract; a typo in either would silently revert
    the routes to weatherless calls."""
    from backend.modules.forecast.lgbm_model import LGBMForecastEngine
    from backend.modules.forecast.mock_engine import MockForecastEngine

    assert LGBMForecastEngine.requires_weather is True
    assert MockForecastEngine.requires_weather is False


def test_the_ingester_requests_every_feature_the_models_use():
    """A variable missing from the Open-Meteo request does not fail -- it
    arrives as NaN and the boosters fall back on a learned default. Seven were
    missing until the models were retrained."""
    from backend.data.ingestion.openmeteo import HOURLY_VARIABLES

    missing = set(feature_builder.WEATHER_FEATURES) - set(HOURLY_VARIABLES)
    assert missing == set(), f"not requested from Open-Meteo: {sorted(missing)}"
