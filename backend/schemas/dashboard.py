from pydantic import BaseModel, ConfigDict
from typing import Optional
from .forecast import ForecastResponse
from .dsm import DSMResponse
from .optimize import ActionCard
from .pooling import PoolingResponse

class DashboardBriefing(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str
    summary: str
    risk_level: str
    total_expected_penalty_inr: float
    potential_savings_inr: float

class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    plant_name: str
    date: str
    avc_mw: float
    forecast: ForecastResponse
    dsm_summary: DSMResponse
    actions: list[ActionCard]
    pooling_benefit: Optional[PoolingResponse] = None
    briefing: DashboardBriefing
