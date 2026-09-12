from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, date

from backend.db.session import get_db
from backend.db.models import JobRun
from backend.core.security import verify_api_key
from backend.modules.pipeline.daily import DailyPipelineOrchestrator
from backend.schemas.pipeline import PipelineRunRequest, PipelineRunResponse

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])
orchestrator = DailyPipelineOrchestrator()

@router.post("/run", response_model=PipelineRunResponse)
def trigger_daily_pipeline(
    request: PipelineRunRequest = PipelineRunRequest(),
    authenticated: bool = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    target_dt = None
    if request.target_date:
        target_dt = datetime.strptime(request.target_date, "%Y-%m-%d").date()
        
    job_run = orchestrator.run_pipeline(db=db, target_date=target_dt)
    return PipelineRunResponse(
        run_id=job_run.id,
        status=job_run.status,
        plants_processed=job_run.plants_processed,
        duration_s=job_run.duration_s,
        error_msg=job_run.error_msg,
        timestamp=job_run.run_time.isoformat(),
    )

@router.get("/status/{run_id}", response_model=PipelineRunResponse)
def get_pipeline_status(run_id: str, db: Session = Depends(get_db)):
    job_run = db.execute(select(JobRun).where(JobRun.id == run_id)).scalar_one_or_none()
    if not job_run:
        raise HTTPException(status_code=404, detail=f"Job run '{run_id}' not found")
    return PipelineRunResponse(
        run_id=job_run.id,
        status=job_run.status,
        plants_processed=job_run.plants_processed,
        duration_s=job_run.duration_s,
        error_msg=job_run.error_msg,
        timestamp=job_run.run_time.isoformat(),
    )
