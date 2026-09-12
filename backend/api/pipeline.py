import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.db.session import SessionLocal, get_db
from backend.db.models import JobRun
from backend.core.security import verify_api_key
from backend.modules.pipeline.daily import DailyPipelineOrchestrator
from backend.schemas.pipeline import PipelineRunRequest, PipelineRunResponse

logger = logging.getLogger("renewable_platform")

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])
orchestrator = DailyPipelineOrchestrator()


def _run_pipeline_background(run_id: str, target_date: Optional[date]) -> None:
    """Execute daily pipeline in background thread with a fresh DB session."""
    with SessionLocal() as db:
        try:
            orchestrator.run_pipeline(db=db, target_date=target_date, run_id=run_id)
        except Exception as e:
            logger.error(f"Background pipeline execution failed for run_id={run_id}: {e}", exc_info=True)


@router.post("/run", response_model=PipelineRunResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_daily_pipeline(
    request: PipelineRunRequest = PipelineRunRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    authenticated: bool = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    target_dt = None
    if request.target_date:
        target_dt = datetime.strptime(request.target_date, "%Y-%m-%d").date()

    run_id = str(uuid.uuid4())
    job_run = JobRun(
        id=run_id,
        run_time=datetime.now(timezone.utc),
        status="accepted",
        plants_processed=0,
        duration_s=0.0,
        error_msg=None,
    )
    db.add(job_run)
    db.commit()

    background_tasks.add_task(_run_pipeline_background, run_id, target_dt)

    return PipelineRunResponse(
        run_id=job_run.id,
        status="accepted",
        plants_processed=0,
        duration_s=None,
        error_msg=None,
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

