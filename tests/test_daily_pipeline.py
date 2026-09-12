import pytest
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.modules.pipeline.daily import DailyPipelineOrchestrator
from backend.db.models import Forecast, Schedule, DSMResult, JobRun

def test_daily_pipeline_execution(db: Session):
    orchestrator = DailyPipelineOrchestrator()
    target_date = date(2026, 6, 1)
    
    job_run = orchestrator.run_pipeline(db=db, target_date=target_date)
    
    assert job_run.status == 'success'
    assert job_run.plants_processed >= 4
    assert job_run.duration_s is not None
    assert job_run.duration_s > 0
    
    # Check DB records created
    forecast_count = len(db.execute(select(Forecast).where(Forecast.run_id == job_run.id)).scalars().all())
    assert forecast_count == 4 * 96
    
    schedule_count = len(db.execute(select(Schedule).where(Schedule.run_id == job_run.id)).scalars().all())
    assert schedule_count == 4 * 96 * 2  # naive_p50 + optimised
    
    dsm_count = len(db.execute(select(DSMResult).where(DSMResult.run_id == job_run.id)).scalars().all())
    assert dsm_count == 4 * 96
