from fastapi import APIRouter
from datetime import datetime

from backend.core.config import load_plants_config, get_settings
from backend.modules.factory import get_forecast_engine
from backend.modules.dsm.engine import DSMEngine
from backend.modules.dsm.pooling import compute_pooling_benefit_by_block, allocate_pool_savings
from backend.schemas.pooling import PoolingRequest, PoolingResponse, PlantPoolAllocation
from backend.modules.forecast.weather_provider import forecast_for

router = APIRouter(prefix="/pooling", tags=["Pooling"])
settings = get_settings()

@router.post("", response_model=PoolingResponse)
def calculate_pooling(request: PoolingRequest):
    forecast_engine = get_forecast_engine()
    all_plants = load_plants_config()
    pool_plants = [p for p in all_plants if p.get("pool_id") == request.pool_id]
    
    if not pool_plants:
        pool_plants = all_plants[:2]
        
    target_date = datetime.strptime(request.date, "%Y-%m-%d").date()
    rule_config_file = f"config/dsm_rules_{request.rule_year}.yaml" if request.rule_year else settings.dsm_rule_config
    try:
        dsm_engine = DSMEngine(config_path=rule_config_file, rule_date=target_date)
    except Exception:
        dsm_engine = DSMEngine(config_path=settings.dsm_rule_config, rule_date=target_date)
        
    # Settled per block. Deviation settles per block under CERC, so a shortfall
    # at 09:00 cannot offset a surplus at 15:00. Passing all 96 blocks of every
    # plant as one flat pool inflates the pool's Available Capacity 96-fold,
    # widens the tolerance band with it, and reports a 100% saving.
    pool_forecasts = {
        p["id"]: forecast_for(forecast_engine, p, request.date)
        for p in pool_plants
    }
    block_count = min((len(v) for v in pool_forecasts.values()), default=0)

    pool_blocks = []
    for b in range(block_count):
        entries = []
        for p in pool_plants:
            fb = pool_forecasts[p["id"]][b]
            entries.append(
                {
                    "plant_id": p["id"],
                    "asset_type": p.get("type", "solar"),
                    "avc_mw": float(p.get("avc_mw", 50.0)),
                    "quantile_forecasts": {
                        0.05: fb["p05"],
                        0.10: fb["p10"],
                        0.25: fb["p25"],
                        0.50: fb["p50"],
                        0.75: fb["p75"],
                        0.90: fb["p90"],
                        0.95: fb["p95"],
                    },
                    "schedule_mw": fb["p50"],
                }
            )
        pool_blocks.append(entries)

    pool_res = compute_pooling_benefit_by_block(
        blocks=pool_blocks,
        dsm_engine=dsm_engine,
        ncd=request.ncd_inr or 450.0,
        freq_hz=request.freq_hz or 50.0,
    )
    
    ind_penalties = {p["plant_id"]: p["individual_inr"] for p in pool_res.get("per_plant", [])}
    allocations_dict = allocate_pool_savings(ind_penalties, pool_res["pooled_total_inr"])
    
    alloc_models = [
        PlantPoolAllocation(
            plant_id=pid,
            individual_penalty_inr=round(ind_penalties[pid], 2),
            allocated_penalty_inr=round(alloc_cost, 2),
            savings_inr=round(ind_penalties[pid] - alloc_cost, 2),
        )
        for pid, alloc_cost in allocations_dict.items()
    ]
    
    return PoolingResponse(
        pool_id=request.pool_id,
        date=request.date,
        individual_total_inr=round(pool_res["individual_total_inr"], 2),
        pooled_total_inr=round(pool_res["pooled_total_inr"], 2),
        savings_inr=round(pool_res["savings_inr"], 2),
        savings_pct=round(pool_res["savings_pct"], 2),
        allocations=alloc_models,
    )
