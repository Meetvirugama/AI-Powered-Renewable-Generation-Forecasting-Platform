from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from backend.db.session import get_db
from backend.core.dates import query_date_or_422
from backend.core.plants import find_plant
from backend.modules.factory import get_forecast_engine
from backend.schemas.forecast import ForecastResponse, BlockForecast
from backend.modules.forecast.weather_provider import forecast_for

router = APIRouter(prefix="/forecast", tags=["Forecast"])

# The brief asks for 24-72 hours, and three horizons are trained. Without this
# the API only ever served 24: every route called the engine with the default 96
# blocks, so the 48h and 72h boosters were loaded into memory, advertised by
# /health as `horizons_trained`, and never reachable.
BLOCKS_PER_HOUR = 4
SUPPORTED_HOURS = (24, 48, 72)


@router.get("", response_model=ForecastResponse)
def get_forecast(
    plant_id: str = Query(..., description="ID of the renewable plant"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    hours: int = Query(
        24,
        description="Forecast horizon in hours: 24, 48 or 72. Longer horizons are "
                    "served by the booster trained for that lead time.",
    ),
    db: Session = Depends(get_db)
):
    if hours not in SUPPORTED_HOURS:
        # Rejected rather than rounded. Silently serving 24 hours to a caller who
        # asked for 72 would be indistinguishable from a working long-range
        # forecast, and the response carries no horizon field to contradict it.
        raise HTTPException(
            status_code=422,
            detail=f"hours must be one of {list(SUPPORTED_HOURS)}; got {hours}",
        )

    num_blocks = hours * BLOCKS_PER_HOUR
    if date is not None:
        # A malformed date previously reached the weather fetch, found no data,
        # and surfaced as an unhandled 500 rather than a client error.
        query_date_or_422(date)
    target_date_str = date or datetime.utcnow().strftime("%Y-%m-%d")
    forecast_engine = get_forecast_engine()
    
    # find_plant already checks the database before the YAML seeds, so the second
    # database lookup that used to follow it here could never find anything new.
    plant_cfg = find_plant(plant_id, db)
    if not plant_cfg:
        raise HTTPException(status_code=404, detail=f"Plant '{plant_id}' not found")
        
    raw_blocks = forecast_for(forecast_engine, plant_cfg, target_date_str, num_blocks)
    
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
