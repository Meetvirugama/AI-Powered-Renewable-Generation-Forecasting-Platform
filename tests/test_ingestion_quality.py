import pytest
import pandas as pd
import numpy as np

from backend.data.quality.resampler import (
    resample_hourly_to_15min,
    add_block_numbers,
    add_ist_columns,
)
from backend.data.quality.validator import (
    validate_weather_data,
    check_avc_exceedance,
    zero_fill_nighttime_solar,
)

def test_resample_hourly_to_15min():
    dates = pd.date_range('2026-01-01 00:00', periods=25, freq='h')
    df_hourly = pd.DataFrame({
        'timestamp': dates,
        'shortwave_radiation': np.linspace(0, 1000, 25),
        'wind_speed_10m': np.linspace(2, 12, 25),
    })
    
    df_15min = resample_hourly_to_15min(df_hourly, time_col='timestamp')
    # 24 hours * 4 blocks/hr + 1 endpoint = 97 rows
    assert len(df_15min) == 97
    assert 'shortwave_radiation' in df_15min.columns

def test_add_block_numbers():
    dates = pd.date_range('2026-01-01 00:00', periods=96, freq='15min')
    df = pd.DataFrame({'timestamp': dates})
    df_blocks = add_block_numbers(df, time_col='timestamp')
    
    assert 'block_no' in df_blocks.columns
    assert df_blocks['block_no'].iloc[0] == 1
    assert df_blocks['block_no'].iloc[-1] == 96
    assert 'ist_time' in df_blocks.columns

def test_validate_weather_data():
    df = pd.DataFrame({
        'shortwave_radiation': [-10.0, 500.0, 800.0, np.nan],
        'temperature_2m': [25.0, 30.0, 75.0, 20.0],  # 75 is outlier
        'wind_speed_10m': [5.0, 10.0, 60.0, 8.0],    # 60 is outlier
        'relative_humidity_2m': [50.0, 110.0, 30.0, 40.0], # 110 clipped to 100
    })
    
    cleaned, flags = validate_weather_data(df)
    assert cleaned['shortwave_radiation'].iloc[0] == 0.0  # negative zeroed
    assert cleaned['relative_humidity_2m'].iloc[1] <= 100.0  # clipped
    assert any(f['column'] == 'temperature_2m' for f in flags)
    assert any(f['column'] == 'wind_speed_10m' for f in flags)

def test_check_avc_exceedance():
    assert check_avc_exceedance(generation_mw=55.0, avc_mw=50.0) is not None
    assert check_avc_exceedance(generation_mw=45.0, avc_mw=50.0) is None

def test_add_ist_columns():
    dates = pd.date_range('2026-01-01 00:00', periods=4, freq='15min')
    df = pd.DataFrame({'timestamp': dates})
    df_ist = add_ist_columns(df, utc_col='timestamp')
    assert 'timestamp_ist' in df_ist.columns
    # UTC 00:00 + 5:30 -> IST 05:30
    assert df_ist['timestamp_ist'].iloc[0].hour == 5
    assert df_ist['timestamp_ist'].iloc[0].minute == 30

def test_zero_fill_nighttime_solar():
    df = pd.DataFrame({
        'shortwave_radiation': [0.0, 500.0, 0.0],
        'direct_normal_irradiance': [100.0, 400.0, 50.0],
        'diffuse_radiation': [50.0, 100.0, 20.0],
    })
    df_filled = zero_fill_nighttime_solar(df, ghi_col='shortwave_radiation')
    assert df_filled['direct_normal_irradiance'].iloc[0] == 0.0
    assert df_filled['direct_normal_irradiance'].iloc[1] == 400.0
    assert df_filled['direct_normal_irradiance'].iloc[2] == 0.0

@pytest.mark.asyncio
async def test_fetch_weather_forecast_mock(monkeypatch):
    import httpx
    from backend.data.ingestion.openmeteo import fetch_weather_forecast, fetch_all_plants_weather

    sample_hourly = {
        "time": ["2026-06-01T00:00", "2026-06-01T01:00"],
        "shortwave_radiation": [0.0, 150.0],
        "wind_speed_10m": [4.5, 5.2]
    }

    class MockResponse:
        def raise_for_status(self): pass
        def json(self): return {"hourly": sample_hourly}

    async def mock_get(self, url, params=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    df = await fetch_weather_forecast(23.0, 72.0, forecast_days=1)
    assert not df.empty
    assert "shortwave_radiation" in df.columns
    assert "timestamp" in df.columns

    plants = [{"id": "GJ_SOLAR_A", "lat": 23.0, "lon": 72.0}]
    all_weather = await fetch_all_plants_weather(plants, forecast_days=1)
    assert "GJ_SOLAR_A" in all_weather
    assert not all_weather["GJ_SOLAR_A"].empty

@pytest.mark.asyncio
async def test_fetch_nasa_power_mock(monkeypatch):
    import httpx
    from backend.data.ingestion.nasa_power import fetch_nasa_power

    sample_nasa_data = {
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {"2026060100": 0.0, "2026060101": 250.0},
                "T2M": {"2026060100": 28.5, "2026060101": 31.0}
            }
        }
    }

    class MockResponse:
        def raise_for_status(self): pass
        def json(self): return sample_nasa_data

    async def mock_get(self, url, params=None, timeout=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    df = await fetch_nasa_power(23.0, 72.0, "20260601", "20260601")
    assert not df.empty
    assert "ALLSKY_SFC_SW_DWN" in df.columns
    assert len(df) == 2

@pytest.mark.asyncio
async def test_fetch_historical_forecast_mock(monkeypatch):
    import httpx
    from backend.data.ingestion.openmeteo_historical import fetch_historical_forecast

    sample_hourly = {
        "time": ["2026-06-01T00:00", "2026-06-01T01:00"],
        "shortwave_radiation": [0.0, 180.0],
        "wind_speed_10m": [5.0, 6.0]
    }

    class MockResponse:
        def raise_for_status(self): pass
        def json(self): return {"hourly": sample_hourly}

    async def mock_get(self, url, params=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    df = await fetch_historical_forecast(23.0, 72.0, "2026-06-01", "2026-06-02")
    assert not df.empty
    assert "shortwave_radiation" in df.columns


