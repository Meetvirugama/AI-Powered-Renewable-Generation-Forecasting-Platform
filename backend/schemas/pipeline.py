from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

from backend.core.dates import validate_iso_date

class PipelineRunRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    target_date: Optional[str] = None

    _target_date = field_validator("target_date")(validate_iso_date)

class PipelineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_id: str
    status: str
    plants_processed: int
    duration_s: Optional[float] = None
    error_msg: Optional[str] = None
    timestamp: str
