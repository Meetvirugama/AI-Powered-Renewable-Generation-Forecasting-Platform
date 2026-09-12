import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from backend.db.session import get_db
from backend.core.config import get_settings
from backend.core.plants import find_plant, list_plants, plants_in_pool
from backend.modules.factory import get_forecast_engine, get_schedule_optimizer
from backend.modules.dsm.engine import DSMEngine
from backend.modules.dsm.pooling import compute_pooling_benefit_by_block, allocate_pool_savings
from backend.schemas.dashboard import DashboardResponse, DashboardBriefing
from backend.schemas.forecast import ForecastResponse, BlockForecast
from backend.schemas.dsm import DSMResponse, BlockDSMResult
from backend.schemas.optimize import ActionCard
from backend.schemas.pooling import PoolingResponse, PlantPoolAllocation
from backend.modules.forecast.weather_provider import forecast_for

logger = logging.getLogger("renewable_platform")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
settings = get_settings()

@router.get("/{plant_id}", response_model=DashboardResponse)
def get_dashboard_data(
    plant_id: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    target_date_str = date or datetime.utcnow().strftime("%Y-%m-%d")
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    forecast_engine = get_forecast_engine()
    optimizer = get_schedule_optimizer()
    
    plant_cfg = find_plant(plant_id, db)
            
    if not plant_cfg:
        plant_cfg = {"id": plant_id, "name": plant_id, "type": "solar", "avc_mw": 50.0, "pool_id": "GJ_POOL_1"}
        
    avc_mw = float(plant_cfg.get("avc_mw", 50.0))
    asset_type = plant_cfg.get("type", "solar")
    plant_name = plant_cfg.get("name", plant_id)
    
    dsm_engine = DSMEngine(config_path=settings.dsm_rule_config, rule_date=target_date)
    raw_forecast = forecast_for(forecast_engine, plant_cfg, target_date_str)
    
    block_forecasts = [
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
        for b in raw_forecast
    ]
    forecast_resp = ForecastResponse(
        plant_id=plant_id,
        date=target_date_str,
        # The engine names itself per block. Hardcoding "mock_lgbm" labelled a
        # real LightGBM forecast as synthetic -- and would equally have labelled
        # a synthetic one as real had the string said otherwise.
        model_name=raw_forecast[0].get("model_name", "mock_lgbm") if raw_forecast else "mock_lgbm",
        blocks=block_forecasts,
    )
    
    opt_result = optimizer.optimize_day_ahead(
        forecast_blocks=raw_forecast,
        avc_mw=avc_mw,
        dsm_engine=dsm_engine,
        ncd=450.0,
        freq_hz=50.0,
        asset_type=asset_type,
    )
    
    dsm_blocks = []
    for i in range(96):
        fb = raw_forecast[i]
        sch = opt_result["optimised_schedule"][i]
        q_dict = {
            0.05: fb["p05"], 0.10: fb["p10"], 0.25: fb["p25"],
            0.50: fb["p50"], 0.75: fb["p75"], 0.90: fb["p90"], 0.95: fb["p95"]
        }
        exp_pen = dsm_engine.compute_expected_penalty(q_dict, sch, avc_mw, 50.0, 450.0, asset_type)
        p50_pen = dsm_engine.compute_block_penalty(fb["p50"], sch, avc_mw, 50.0, 450.0, asset_type)
        dev_pct = dsm_engine.compute_deviation_pct(fb["p50"], sch, avc_mw)
        dsm_blocks.append(
            BlockDSMResult(
                block_no=i+1,
                expected_penalty_inr=round(exp_pen, 2),
                p50_penalty_inr=round(p50_pen, 2),
                schedule_mw=round(sch, 2),
                deviation_pct_at_p50=round(dev_pct, 2),
            )
        )
        
    dsm_summary = DSMResponse(
        plant_id=plant_id,
        date=target_date_str,
        rule_version=dsm_engine.config.rule_version,
        x_value=round(dsm_engine.x, 2),
        total_expected_penalty_inr=round(opt_result["optimised_total_inr"], 2),
        total_p50_penalty_inr=round(opt_result["naive_total_inr"], 2),
        blocks=dsm_blocks,
    )
    
    actions = [
        ActionCard(
            type=c["type"],
            block_no=c["block_no"],
            mw=c["mw"],
            reason=c["reason"],
            inr_impact=c["inr_impact"],
        )
        for c in opt_result.get("action_cards", [])
    ]
    
    pool_id = plant_cfg.get("pool_id", "GJ_POOL_1")
    pooling_resp = None
    try:
        pool_plants = plants_in_pool(pool_id, db)
        if pool_plants:
            # Settled per block, not as one flat list of plant-blocks. Deviation
            # settles per block under CERC, and collapsing the day into a single
            # call inflates the pool's AvC (and so its tolerance band) 96-fold,
            # which drove the pooled penalty to zero and reported a 100% saving.
            pool_forecasts = {
                p["id"]: forecast_for(forecast_engine, p, target_date_str)
                for p in pool_plants
            }
            block_count = min((len(v) for v in pool_forecasts.values()), default=0)

            pool_blocks = []
            for b in range(block_count):
                entries = []
                for p in pool_plants:
                    fb = pool_forecasts[p["id"]][b]
                    entries.append({
                        "plant_id": p["id"],
                        "asset_type": p.get("type", "solar"),
                        "avc_mw": float(p.get("avc_mw", 50.0)),
                        "quantile_forecasts": {
                            0.05: fb["p05"], 0.10: fb["p10"], 0.25: fb["p25"],
                            0.50: fb["p50"], 0.75: fb["p75"], 0.90: fb["p90"], 0.95: fb["p95"],
                        },
                        "schedule_mw": fb["p50"],
                    })
                pool_blocks.append(entries)

            pres = compute_pooling_benefit_by_block(pool_blocks, dsm_engine, 450.0, 50.0)
            ind_penalties = {p["plant_id"]: p["individual_inr"] for p in pres.get("per_plant", [])}
            allocs = allocate_pool_savings(ind_penalties, pres["pooled_total_inr"])
            alloc_models = [
                PlantPoolAllocation(
                    plant_id=pid,
                    individual_penalty_inr=round(ind_penalties[pid], 2),
                    allocated_penalty_inr=round(acost, 2),
                    savings_inr=round(ind_penalties[pid] - acost, 2),
                )
                for pid, acost in allocs.items()
            ]
            pooling_resp = PoolingResponse(
                pool_id=pool_id,
                date=target_date_str,
                individual_total_inr=round(pres["individual_total_inr"], 2),
                pooled_total_inr=round(pres["pooled_total_inr"], 2),
                savings_inr=round(pres["savings_inr"], 2),
                savings_pct=round(pres["savings_pct"], 2),
                allocations=alloc_models,
            )
    except Exception as exc:
        # Pooling is supplementary to the dashboard, so a failure here must not
        # take the whole page down -- but it must not vanish either. Silently
        # swallowing this is how a 100% pooling saving stayed on screen.
        logger.warning("pooling benefit unavailable for pool %s: %s", pool_id, exc)

    risk_lvl = "MODERATE"
    if opt_result["savings_pct"] > 30:
        risk_lvl = "HIGH_SAVINGS_OPPORTUNITY"
        
    briefing = DashboardBriefing(
        title=f"Daily DSM Briefing — {plant_name}",
        summary=f"Optimized schedule saves ₹{opt_result['savings_inr']:,.2f} ({opt_result['savings_pct']:.1f}%) compared to naive P50 submission under CERC 2026 rules.",
        risk_level=risk_lvl,
        total_expected_penalty_inr=round(opt_result["optimised_total_inr"], 2),
        potential_savings_inr=round(opt_result["savings_inr"], 2),
    )
    
    return DashboardResponse(
        plant_id=plant_id,
        plant_name=plant_name,
        date=target_date_str,
        avc_mw=avc_mw,
        forecast=forecast_resp,
        dsm_summary=dsm_summary,
        actions=actions,
        pooling_benefit=pooling_resp,
        briefing=briefing,
    )
