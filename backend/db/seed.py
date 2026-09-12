from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.core.config import load_plants_config
from backend.db.models import Plant
import logging

logger = logging.getLogger("renewable_platform")

def seed_plants(db: Session) -> int:
    """
    Loads plants from the configuration file and upserts them into the database.
    Returns the count of plants processed.
    """
    plants_config = load_plants_config()
    count = 0
    
    for plant_data in plants_config:
        plant_id = plant_data.get("id")
        if not plant_id:
            continue
            
        existing_plant = db.execute(select(Plant).where(Plant.id == plant_id)).scalar_one_or_none()
        
        type_val = str(plant_data.get("type", "solar")).lower()
        lat_val = float(plant_data.get("lat", plant_data.get("latitude", 0.0)))
        lon_val = float(plant_data.get("lon", plant_data.get("longitude", 0.0)))
        avc_val = float(plant_data.get("avc_mw", plant_data.get("capacity_mw_avc", 0.0)))
        
        metadata_dict = {
            "tilt_deg": plant_data.get("tilt_deg", plant_data.get("tilt")),
            "azimuth_deg": plant_data.get("azimuth_deg", plant_data.get("azimuth")),
            "hub_height_m": plant_data.get("hub_height_m"),
            "rotor_diameter_m": plant_data.get("rotor_diameter_m"),
            "technology": plant_data.get("technology"),
            "power_curve": plant_data.get("power_curve"),
        }
        
        if not existing_plant:
            new_plant = Plant(
                id=plant_id,
                name=plant_data.get("name", plant_id),
                type=type_val,
                lat=lat_val,
                lon=lon_val,
                avc_mw=avc_val,
                pool_id=plant_data.get("pool_id", "GJ_POOL_1"),
                metadata_json=metadata_dict,
            )
            db.add(new_plant)
            count += 1
            logger.info(f"Seeded new plant: {plant_id}")
        else:
            existing_plant.name = plant_data.get("name", existing_plant.name)
            existing_plant.type = type_val
            existing_plant.lat = lat_val
            existing_plant.lon = lon_val
            existing_plant.avc_mw = avc_val
            existing_plant.pool_id = plant_data.get("pool_id", existing_plant.pool_id)
            existing_plant.metadata_json = metadata_dict
            
    db.commit()
    return count
