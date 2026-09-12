from fastapi import APIRouter
from datetime import datetime

from backend.core.config import load_plants_config, get_settings
from backend.modules.factory import get_forecast_engine, get_schedule_optimizer
from backend.modules.dsm.engine import DSMEngine
from backend.schemas.optimize import OptimizeRequest, OptimizeResponse, BatteryDispatchBlock, ActionCard
from backend.modules.forecast.weather_provider import forecast_for

router = APIRouter(prefix="/optimize", tags=["Optimization"])
settings = get_settings()

@router.post("", response_model=OptimizeResponse)
def optimize_schedule(request: OptimizeRequest):
    forecast_engine = get_forecast_engine()
    optimizer = get_schedule_optimizer()
    plant_cfg = None
    for p in load_plants_config():
        if p["id"] == request.plant_id:
            plant_cfg = p
            break
            
    if not plant_cfg:
        plant_cfg = {"id": request.plant_id, "type": "solar", "avc_mw": 50.0, "lat": 23.0, "lon": 72.0}
        
    avc_mw = float(plant_cfg.get("avc_mw", 50.0))
    asset_type = plant_cfg.get("type", "solar")
    target_date = datetime.strptime(request.date, "%Y-%m-%d").date()
    
    rule_config_file = f"config/dsm_rules_{request.rule_year}.yaml" if request.rule_year else settings.dsm_rule_config
    try:
        dsm_engine = DSMEngine(config_path=rule_config_file, rule_date=target_date)
    except Exception:
        dsm_engine = DSMEngine(config_path=settings.dsm_rule_config, rule_date=target_date)
        
    forecast_blocks = forecast_for(forecast_engine, plant_cfg, request.date)
    
    opt_result = optimizer.optimize_day_ahead(
        forecast_blocks=forecast_blocks,
        avc_mw=avc_mw,
        dsm_engine=dsm_engine,
        ncd=request.ncd_inr or 450.0,
        freq_hz=request.freq_hz or 50.0,
        asset_type=asset_type,
        battery_capacity_mwh=float(request.battery_capacity_mwh or 0.0),
    )
    
    battery_blocks = [
        BatteryDispatchBlock(
            block_no=b["block_no"],
            charge_mw=b["charge_mw"],
            discharge_mw=b["discharge_mw"],
            soc_mwh=b["soc_mwh"],
        )
        for b in opt_result.get("battery_dispatch", [])
    ]
    
    action_cards = [
        ActionCard(
            type=c["type"],
            block_no=c["block_no"],
            mw=c["mw"],
            reason=c["reason"],
            inr_impact=c["inr_impact"],
        )
        for c in opt_result.get("action_cards", [])
    ]
    
    return OptimizeResponse(
        plant_id=request.plant_id,
        date=request.date,
        rule_version=dsm_engine.config.rule_version,
        naive_total_inr=round(opt_result["naive_total_inr"], 2),
        optimised_total_inr=round(opt_result["optimised_total_inr"], 2),
        savings_inr=round(opt_result["savings_inr"], 2),
        savings_pct=round(opt_result["savings_pct"], 2),
        optimised_schedule=[round(s, 2) for s in opt_result["optimised_schedule"]],
        naive_schedule=[round(s, 2) for s in opt_result["naive_schedule"]],
        battery_dispatch=battery_blocks,
        action_cards=action_cards,
    )
