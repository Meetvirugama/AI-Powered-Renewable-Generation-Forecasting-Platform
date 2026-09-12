from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.core.plants import find_plant, list_plants
from backend.schemas.plant import PlantListResponse, PlantResponse, PlantMetadata

router = APIRouter(prefix="/plants", tags=["Plants"])


def _response(plant: dict) -> PlantResponse:
    """One response shape for database rows and YAML seeds alike.

    The resolver flattens site parameters to the top level for both sources, and
    PlantMetadata picks the fields it declares and ignores the rest, so no branch
    on where the plant came from is needed here.
    """
    return PlantResponse(
        id=plant["id"],
        name=plant["name"],
        type=plant["type"],
        lat=plant["lat"],
        lon=plant["lon"],
        avc_mw=plant["avc_mw"],
        pool_id=plant.get("pool_id"),
        metadata_json=PlantMetadata(**plant),
    )


@router.get("", response_model=PlantListResponse)
def get_plants(db: Session = Depends(get_db)):
    # Through the shared resolver, like every other route. This route used to read
    # the table itself, which is why it was the only one listing the invented
    # seed plants beside the imported inventory.
    plants = [_response(p) for p in list_plants(db)]
    return PlantListResponse(plants=plants, total=len(plants))


@router.get("/{plant_id}", response_model=PlantResponse)
def get_plant(plant_id: str, db: Session = Depends(get_db)):
    plant = find_plant(plant_id, db)
    if not plant:
        raise HTTPException(status_code=404, detail=f"Plant '{plant_id}' not found")
    return _response(plant)
