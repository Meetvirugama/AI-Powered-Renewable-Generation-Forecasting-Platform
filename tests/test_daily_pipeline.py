from datetime import date
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.modules.pipeline.daily import DailyPipelineOrchestrator
from backend.db.models import Forecast, Schedule, DSMResult, WeatherForecast


def test_daily_pipeline_execution(db: Session, monkeypatch):
    sample_hourly = {
        "time": [f"2026-06-01T{h:02d}:00" for h in range(24)] + ["2026-06-02T00:00"],
        "shortwave_radiation": [100.0] * 25,
        "direct_normal_irradiance": [200.0] * 25,
        "diffuse_radiation": [50.0] * 25,
        "wind_speed_10m": [5.0] * 25,
        "wind_speed_80m": [7.0] * 25,
        "wind_speed_120m": [8.0] * 25,
        "temperature_2m": [25.0] * 25,
        "relative_humidity_2m": [50.0] * 25,
        "cloud_cover": [20.0] * 25,
    }

    class MockResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"hourly": sample_hourly}

    async def mock_get(self, url, params=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    orchestrator = DailyPipelineOrchestrator()
    target_date = date(2026, 6, 1)

    job_run = orchestrator.run_pipeline(db=db, target_date=target_date)

    assert job_run.status == "success"
    assert job_run.plants_processed >= 4
    assert job_run.duration_s is not None
    assert job_run.duration_s > 0

    # Check WeatherForecast records created
    weather_count = len(db.execute(select(WeatherForecast)).scalars().all())
    assert weather_count >= 4 * 96

    # Check Forecast DB records created
    forecast_count = len(db.execute(select(Forecast).where(Forecast.run_id == job_run.id)).scalars().all())
    assert forecast_count == 4 * 96

    schedule_count = len(db.execute(select(Schedule).where(Schedule.run_id == job_run.id)).scalars().all())
    assert schedule_count == 4 * 96 * 2  # naive_p50 + optimised

    dsm_count = len(db.execute(select(DSMResult).where(DSMResult.run_id == job_run.id)).scalars().all())
    assert dsm_count == 4 * 96

