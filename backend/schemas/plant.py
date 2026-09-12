from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, Union

class PlantMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tilt_deg: Optional[float] = None
    azimuth_deg: Optional[float] = None
    hub_height_m: Optional[float] = None
    rotor_diameter_m: Optional[float] = None
    technology: Optional[str] = None
    power_curve: Optional[Union[str, list, Any]] = None

class PlantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    type: str
    lat: float
    lon: float
    avc_mw: float
    pool_id: Optional[str] = None
    metadata_json: Optional[PlantMetadata] = None

class PlantListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plants: list[PlantResponse]
    total: int
