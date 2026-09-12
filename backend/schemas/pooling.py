from pydantic import BaseModel, ConfigDict
from typing import Optional

class PlantPoolAllocation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    individual_penalty_inr: float
    allocated_penalty_inr: float
    savings_inr: float

class PoolingRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pool_id: str
    date: str
    rule_year: Optional[int] = 2026
    freq_hz: Optional[float] = 50.0
    ncd_inr: Optional[float] = 450.0

class PoolingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pool_id: str
    date: str
    individual_total_inr: float
    pooled_total_inr: float
    savings_inr: float
    savings_pct: float
    allocations: list[PlantPoolAllocation]
