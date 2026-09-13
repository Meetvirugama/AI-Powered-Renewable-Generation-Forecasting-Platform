from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

from backend.core.dates import validate_iso_date

class PlantPoolAllocation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    # The display name. The panel used to print plant_id, which for an imported
    # plant is an OpenStreetMap id such as OSM_W1273382001.
    plant_name: Optional[str] = None
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

    _date = field_validator("date")(validate_iso_date)

class PoolingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pool_id: str
    date: str
    individual_total_inr: float
    pooled_total_inr: float
    savings_inr: float
    savings_pct: float
    allocations: list[PlantPoolAllocation]
    # How many plants share the pool. A pool of one nets nothing, and the panel
    # used to present it as "settled as one pool, 0.0% saved".
    pool_size: int = 0
