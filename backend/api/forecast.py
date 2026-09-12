from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional
from datetime import datetime

from backend.db.session import get_db
from backend.db.models import Plant
from backend.core.plants import find_plant
from backend.modules.factory import get_forecast_engine
from backend.schemas.forecast import ForecastResponse, BlockForecast
from backend.modules.forecast.weather_provider import forecast_for

router = APIRouter(prefix="/forecast", tags=["Forecast"])

@router.get("", response_model=ForecastResponse)
def get_forecast(
    plant_id: str = Query(..., description="ID of the renewable plant"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    target_date_str = date or datetime.utcnow().strftime("%Y-%m-%d")
    forecast_engine = get_forecast_engine()
    
    plant_cfg = find_plant(plant_id, db)
            
    if not plant_cfg:
        plant_db = db.execute(select(Plant).where(Plant.id == plant_id)).scalar_one_or_none()
        if plant_db:
            plant_cfg = {
                "id": plant_db.id,
                "name": plant_db.name,
                "type": plant_db.type,
                "lat": plant_db.lat,
                "lon": plant_db.lon,
                "avc_mw": plant_db.avc_mw,
                "pool_id": plant_db.pool_id,
            }
            
    if not plant_cfg:
        raise HTTPException(status_code=404, detail=f"Plant '{plant_id}' not found")
        
    raw_blocks = forecast_for(forecast_engine, plant_cfg, target_date_str)
    
    block_models = [
        BlockForecast(
            block_no=b["block_no"],
            valid_time=b["valid_time"],
            ist_time=b.get("ist_time", f"{((b['block_no']-1)*15)//60:02d}:{((b['block_no']-1)*15)%60:02d}"),
            p05=round(b["p05"], 2),
            p10=round(b["p10"], 2),
            p25=round(b["p25"], 2),
            p50=round(b["p50"], 2),
            p75=round(b["p75"], 2),
            p90=round(b["p90"], 2),
            p95=round(b["p95"], 2),
        )
        for b in raw_blocks
    ]
    
    return ForecastResponse(
        plant_id=plant_id,
        date=target_date_str,
        # The engine names itself per block. Hardcoding "mock_lgbm" labelled a
        # real LightGBM forecast as synthetic -- and would equally have labelled
        # a synthetic one as real had the string said otherwise.
        model_name=raw_blocks[0].get("model_name", "mock_lgbm") if raw_blocks else "mock_lgbm",
        blocks=block_models,
    )
