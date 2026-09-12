from fastapi import APIRouter
from datetime import datetime

from backend.core.config import load_plants_config, get_settings
from backend.modules.factory import get_forecast_engine
from backend.modules.dsm.engine import DSMEngine
from backend.schemas.dsm import DSMRequest, DSMResponse, BlockDSMResult
from backend.modules.forecast.weather_provider import forecast_for

router = APIRouter(prefix="/dsm", tags=["DSM"])
settings = get_settings()

@router.post("", response_model=DSMResponse)
def calculate_dsm(request: DSMRequest):
    forecast_engine = get_forecast_engine()
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
    
    blocks_result: list[BlockDSMResult] = []
    total_exp = 0.0
    total_p50 = 0.0
    
    sch_len = len(request.schedule_mw)
    for i in range(96):
        sch = request.schedule_mw[i] if i < sch_len else 0.0
        fb = forecast_blocks[i]
        
        q_dict = {
            0.05: fb["p05"],
            0.10: fb["p10"],
            0.25: fb["p25"],
            0.50: fb["p50"],
            0.75: fb["p75"],
            0.90: fb["p90"],
            0.95: fb["p95"],
        }
        
        exp_pen = dsm_engine.compute_expected_penalty(
            quantile_forecasts=q_dict,
            schedule_mw=sch,
            avc_mw=avc_mw,
            freq_hz=request.freq_hz or 50.0,
            ncd=request.ncd_inr or 450.0,
            asset_type=asset_type,
        )
        p50_pen = dsm_engine.compute_block_penalty(
            actual_mw=fb["p50"],
            schedule_mw=sch,
            avc_mw=avc_mw,
            freq_hz=request.freq_hz or 50.0,
            ncd_inr_per_mwh=request.ncd_inr or 450.0,
            asset_type=asset_type,
        )
        dev_pct = dsm_engine.compute_deviation_pct(fb["p50"], sch, avc_mw)
        
        total_exp += exp_pen
        total_p50 += p50_pen
        
        blocks_result.append(
            BlockDSMResult(
                block_no=i + 1,
                expected_penalty_inr=round(exp_pen, 2),
                p50_penalty_inr=round(p50_pen, 2),
                schedule_mw=round(sch, 2),
                deviation_pct_at_p50=round(dev_pct, 2),
            )
        )
        
    return DSMResponse(
        plant_id=request.plant_id,
        date=request.date,
        rule_version=dsm_engine.config.rule_version,
        x_value=round(dsm_engine.x, 2),
        total_expected_penalty_inr=round(total_exp, 2),
        total_p50_penalty_inr=round(total_p50, 2),
        blocks=blocks_result,
    )
