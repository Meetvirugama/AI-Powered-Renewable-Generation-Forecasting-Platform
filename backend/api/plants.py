from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.db.session import get_db
from backend.db.models import Plant
from backend.core.config import load_plants_config
from backend.schemas.plant import PlantListResponse, PlantResponse, PlantMetadata

router = APIRouter(prefix="/plants", tags=["Plants"])

@router.get("", response_model=PlantListResponse)
def get_plants(db: Session = Depends(get_db)):
    plants_db = db.execute(select(Plant)).scalars().all()
    if not plants_db:
        cfg_plants = load_plants_config()
        responses = [
            PlantResponse(
                id=p["id"],
                name=p["name"],
                type=p["type"],
                lat=p["lat"],
                lon=p["lon"],
                avc_mw=p["avc_mw"],
                pool_id=p.get("pool_id"),
                metadata_json=PlantMetadata(
                    tilt_deg=p.get("tilt_deg"),
                    azimuth_deg=p.get("azimuth_deg"),
                    hub_height_m=p.get("hub_height_m"),
                    rotor_diameter_m=p.get("rotor_diameter_m"),
                    technology=p.get("technology"),
                    power_curve=p.get("power_curve"),
                ),
            )
            for p in cfg_plants
        ]
        return PlantListResponse(plants=responses, total=len(responses))
    
    responses = [
        PlantResponse(
            id=p.id,
            name=p.name,
            type=p.type,
            lat=p.lat,
            lon=p.lon,
            avc_mw=p.avc_mw,
            pool_id=p.pool_id,
            metadata_json=PlantMetadata(**(p.metadata_json or {})),
        )
        for p in plants_db
    ]
    return PlantListResponse(plants=responses, total=len(responses))

@router.get("/{plant_id}", response_model=PlantResponse)
def get_plant(plant_id: str, db: Session = Depends(get_db)):
    plant = db.execute(select(Plant).where(Plant.id == plant_id)).scalar_one_or_none()
    if plant:
        return PlantResponse(
            id=plant.id,
            name=plant.name,
            type=plant.type,
            lat=plant.lat,
            lon=plant.lon,
            avc_mw=plant.avc_mw,
            pool_id=plant.pool_id,
            metadata_json=PlantMetadata(**(plant.metadata_json or {})),
        )
    
    cfg_plants = load_plants_config()
    for p in cfg_plants:
        if p["id"] == plant_id:
            return PlantResponse(
                id=p["id"],
                name=p["name"],
                type=p["type"],
                lat=p["lat"],
                lon=p["lon"],
                avc_mw=p["avc_mw"],
                pool_id=p.get("pool_id"),
                metadata_json=PlantMetadata(
                    tilt_deg=p.get("tilt_deg"),
                    azimuth_deg=p.get("azimuth_deg"),
                    hub_height_m=p.get("hub_height_m"),
                    rotor_diameter_m=p.get("rotor_diameter_m"),
                    technology=p.get("technology"),
                    power_curve=p.get("power_curve"),
                ),
            )
    raise HTTPException(status_code=404, detail=f"Plant '{plant_id}' not found")
