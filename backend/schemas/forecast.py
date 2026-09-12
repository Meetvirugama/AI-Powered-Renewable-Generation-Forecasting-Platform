from pydantic import BaseModel, ConfigDict

class BlockForecast(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    block_no: int
    valid_time: str
    ist_time: str
    p05: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p95: float

class ForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    date: str
    model_name: str
    blocks: list[BlockForecast]
