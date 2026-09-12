from pydantic import BaseModel, ConfigDict
from typing import Optional

class ActionCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: str
    block_no: int
    mw: float
    reason: str
    inr_impact: float

class BatteryDispatchBlock(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    block_no: int
    charge_mw: float
    discharge_mw: float
    soc_mwh: float

class OptimizeRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    date: str
    rule_year: Optional[int] = 2026
    freq_hz: Optional[float] = 50.0
    ncd_inr: Optional[float] = 450.0
    battery_capacity_mwh: Optional[float] = None

class OptimizeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    date: str
    rule_version: str
    naive_total_inr: float
    optimised_total_inr: float
    savings_inr: float
    savings_pct: float
    optimised_schedule: list[float]
    naive_schedule: list[float]
    battery_dispatch: list[BatteryDispatchBlock]
    action_cards: list[ActionCard]
