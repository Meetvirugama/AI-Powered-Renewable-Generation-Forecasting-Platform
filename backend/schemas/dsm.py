from pydantic import BaseModel, ConfigDict
from typing import Optional

class DSMRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    date: str
    schedule_mw: list[float] = []
    rule_year: Optional[int] = 2026
    freq_hz: Optional[float] = 50.0
    ncd_inr: Optional[float] = 450.0

class BlockDSMResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    block_no: int
    expected_penalty_inr: float
    p50_penalty_inr: float
    schedule_mw: float
    deviation_pct_at_p50: float

class DSMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    date: str
    rule_version: str
    x_value: float
    total_expected_penalty_inr: float
    total_p50_penalty_inr: float
    blocks: list[BlockDSMResult]
