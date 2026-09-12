from fastapi import APIRouter
from datetime import datetime

from backend.core.config import load_plants_config, get_settings
from backend.modules.factory import get_forecast_engine
from backend.modules.dsm.engine import DSMEngine
from backend.modules.dsm.pooling import compute_pooling_benefit, allocate_pool_savings
from backend.schemas.pooling import PoolingRequest, PoolingResponse, PlantPoolAllocation

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
        
    plants_data = []
    for p in pool_plants:
        fbs = forecast_engine.generate_forecast(plant=p, date_str=request.date, num_blocks=96)
        for fb in fbs:
            q_dict = {
                0.05: fb["p05"],
                0.10: fb["p10"],
                0.25: fb["p25"],
                0.50: fb["p50"],
                0.75: fb["p75"],
                0.90: fb["p90"],
                0.95: fb["p95"],
            }
            plants_data.append(
                {
                    "plant_id": p["id"],
                    "asset_type": p.get("type", "solar"),
                    "avc_mw": float(p.get("avc_mw", 50.0)),
                    "quantile_forecasts": q_dict,
                    "schedule_mw": fb["p50"],
                }
            )
            
    pool_res = compute_pooling_benefit(
        plants_data=plants_data,
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
