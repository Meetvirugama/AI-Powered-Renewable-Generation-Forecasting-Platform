import time
import uuid
import logging
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.core.config import load_plants_config, get_settings
from backend.db.models import (
    Plant,
    Forecast,
    Schedule,
    DSMResult,
    Action,
    PoolingResult,
    JobRun,
)
from backend.modules.factory import get_forecast_engine, get_schedule_optimizer
from backend.modules.dsm.engine import DSMEngine
from backend.modules.dsm.pooling import compute_pooling_benefit

logger = logging.getLogger("renewable_platform")


class DailyPipelineOrchestrator:
    """
    Orchestrates the end-to-end 9-step daily forecasting and scheduling pipeline.
    """

    def __init__(self, forecast_engine=None, optimizer=None):
        self.forecast_engine = forecast_engine or get_forecast_engine()
        self.optimizer = optimizer or get_schedule_optimizer()
        self.settings = get_settings()

    def run_pipeline(
        self, db: Session, target_date: Optional[date] = None
    ) -> JobRun:
        if target_date is None:
            target_date = date.today()

        run_id = str(uuid.uuid4())
        date_str = target_date.strftime("%Y-%m-%d")
        start_time = time.time()

        job_run = JobRun(
            id=run_id,
            run_time=datetime.now(timezone.utc),
            status="running",
            plants_processed=0,
            duration_s=0.0,
            error_msg=None,
        )
        db.add(job_run)
        db.commit()

        logger.info(f"Starting Daily Pipeline run_id={run_id} for date={date_str}")

        try:
            plants_cfg = load_plants_config()
            if not plants_cfg:
                plants_db = db.execute(select(Plant)).scalars().all()
                plants_cfg = [
                    {
                        "id": p.id,
                        "name": p.name,
                        "type": p.type,
                        "lat": p.lat,
                        "lon": p.lon,
                        "avc_mw": p.avc_mw,
                        "pool_id": p.pool_id,
                    }
                    for p in plants_db
                ]

            dsm_engine = DSMEngine(
                config_path=self.settings.dsm_rule_config, rule_date=target_date
            )

            all_forecasts_by_plant: dict[str, list[dict]] = {}
            all_schedules_by_plant: dict[str, list[float]] = {}
            all_plants_meta: dict[str, dict] = {}

            for plant in plants_cfg:
                plant_id = plant["id"]
                asset_type = plant.get("type", "solar")
                avc_mw = float(plant.get("avc_mw", 50.0))
                all_plants_meta[plant_id] = plant

                forecast_blocks = self.forecast_engine.generate_forecast(
                    plant=plant, date_str=date_str, num_blocks=96
                )
                all_forecasts_by_plant[plant_id] = forecast_blocks

                for fb in forecast_blocks:
                    valid_dt = datetime.fromisoformat(fb["valid_time"])
                    f_record = Forecast(
                        plant_id=plant_id,
                        run_id=run_id,
                        valid_time=valid_dt,
                        block_no=fb["block_no"],
                        model_name=fb.get("model_name", "mock_lgbm"),
                        p05=fb["p05"],
                        p10=fb["p10"],
                        p25=fb["p25"],
                        p50=fb["p50"],
                        p75=fb["p75"],
                        p90=fb["p90"],
                        p95=fb["p95"],
                        calibrated=True,
                    )
                    db.add(f_record)

                opt_result = self.optimizer.optimize_day_ahead(
                    forecast_blocks=forecast_blocks,
                    avc_mw=avc_mw,
                    dsm_engine=dsm_engine,
                    ncd=450.0,
                    freq_hz=50.0,
                    asset_type=asset_type,
                )
                all_schedules_by_plant[plant_id] = opt_result["optimised_schedule"]

                for blk_idx in range(96):
                    block_no = blk_idx + 1
                    naive_sch = opt_result["naive_schedule"][blk_idx]
                    opt_sch = opt_result["optimised_schedule"][blk_idx]

                    db.add(
                        Schedule(
                            plant_id=plant_id,
                            schedule_date=target_date,
                            block_no=block_no,
                            schedule_type="naive_p50",
                            schedule_mw=naive_sch,
                            run_id=run_id,
                        )
                    )
                    db.add(
                        Schedule(
                            plant_id=plant_id,
                            schedule_date=target_date,
                            block_no=block_no,
                            schedule_type="optimised",
                            schedule_mw=opt_sch,
                            run_id=run_id,
                        )
                    )

                    fb = forecast_blocks[blk_idx]
                    valid_dt = datetime.fromisoformat(fb["valid_time"])
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
                        schedule_mw=opt_sch,
                        avc_mw=avc_mw,
                        freq_hz=50.0,
                        ncd=450.0,
                        asset_type=asset_type,
                    )
                    p50_pen = dsm_engine.compute_block_penalty(
                        actual_mw=fb["p50"],
                        schedule_mw=opt_sch,
                        avc_mw=avc_mw,
                        freq_hz=50.0,
                        ncd_inr_per_mwh=450.0,
                        asset_type=asset_type,
                    )

                    db.add(
                        DSMResult(
                            plant_id=plant_id,
                            run_id=run_id,
                            valid_time=valid_dt,
                            block_no=block_no,
                            schedule_mw=opt_sch,
                            expected_penalty_inr=exp_pen,
                            p50_penalty_inr=p50_pen,
                            optimised_penalty_inr=exp_pen,
                            rule_version=dsm_engine.config.rule_version,
                            x_value=dsm_engine.x,
                            savings_inr=max(0.0, p50_pen - exp_pen),
                        )
                    )

                for card in opt_result.get("action_cards", []):
                    blk_no = card.get("block_no", 1)
                    fb = forecast_blocks[blk_no - 1]
                    valid_dt = datetime.fromisoformat(fb["valid_time"])
                    db.add(
                        Action(
                            plant_id=plant_id,
                            run_id=run_id,
                            valid_time=valid_dt,
                            block_no=blk_no,
                            action_type=card.get("type", "curtailment"),
                            action_mw=card.get("mw", 0.0),
                            soc_mwh=None,
                            reason=card.get("reason", ""),
                        )
                    )

            pools: dict[str, list[dict]] = {}
            for plant in plants_cfg:
                pid = plant.get("pool_id", "DEFAULT_POOL")
                pools.setdefault(pid, []).append(plant)

            for pool_id, pool_plants in pools.items():
                pooling_input = []
                for p in pool_plants:
                    p_id = p["id"]
                    fbs = all_forecasts_by_plant[p_id]
                    schs = all_schedules_by_plant[p_id]
                    for blk_idx in range(96):
                        fb = fbs[blk_idx]
                        q_dict = {
                            0.05: fb["p05"],
                            0.10: fb["p10"],
                            0.25: fb["p25"],
                            0.50: fb["p50"],
                            0.75: fb["p75"],
                            0.90: fb["p90"],
                            0.95: fb["p95"],
                        }
                        pooling_input.append(
                            {
                                "plant_id": p_id,
                                "asset_type": p.get("type", "solar"),
                                "avc_mw": float(p.get("avc_mw", 50.0)),
                                "quantile_forecasts": q_dict,
                                "schedule_mw": schs[blk_idx],
                            }
                        )

                pool_res = compute_pooling_benefit(
                    plants_data=pooling_input,
                    dsm_engine=dsm_engine,
                    ncd=450.0,
                    freq_hz=50.0,
                )

                db.add(
                    PoolingResult(
                        pool_id=pool_id,
                        run_id=run_id,
                        schedule_date=target_date,
                        individual_penalty_inr=pool_res["individual_total_inr"],
                        pooled_penalty_inr=pool_res["pooled_total_inr"],
                        savings_pct=pool_res["savings_pct"],
                    )
                )

            db.commit()

            duration = time.time() - start_time
            job_run.status = "success"
            job_run.plants_processed = len(plants_cfg)
            job_run.duration_s = round(duration, 3)
            db.commit()

            logger.info(
                f"Daily Pipeline run_id={run_id} completed successfully in {duration:.2f}s for {len(plants_cfg)} plants."
            )
            return job_run

        except Exception as e:
            db.rollback()
            duration = time.time() - start_time
            job_run.status = "failed"
            job_run.error_msg = str(e)
            job_run.duration_s = round(duration, 3)
            try:
                db.add(job_run)
                db.commit()
            except Exception:
                db.rollback()
            logger.error(f"Daily Pipeline run_id={run_id} failed: {e}", exc_info=True)
            raise e
