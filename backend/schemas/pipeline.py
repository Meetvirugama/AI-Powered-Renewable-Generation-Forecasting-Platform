from pydantic import BaseModel, ConfigDict
from typing import Optional

class PipelineRunRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    target_date: Optional[str] = None

class PipelineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_id: str
    status: str
    plants_processed: int
    duration_s: Optional[float] = None
    error_msg: Optional[str] = None
    timestamp: str
