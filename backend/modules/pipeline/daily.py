import asyncio
import time
import uuid
import logging
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd
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
    WeatherForecast,
)
from backend.modules.factory import get_forecast_engine, get_schedule_optimizer
from backend.modules.dsm.engine import DSMEngine
from backend.modules.dsm.pooling import compute_pooling_benefit
from backend.data.ingestion.openmeteo import fetch_weather_forecast
from backend.data.quality.validator import validate_weather_data, zero_fill_nighttime_solar
from backend.data.quality.resampler import (
    resample_hourly_to_15min,
    add_block_numbers,
    add_ist_columns,
)

logger = logging.getLogger("renewable_platform")


def _run_async(coro):
    """Safely execute an async coroutine across sync threads and running event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


class DailyPipelineOrchestrator:
    """
    Orchestrates the end-to-end 9-step daily forecasting and scheduling pipeline.
    """

    def __init__(self, forecast_engine=None, optimizer=None):
        self.forecast_engine = forecast_engine or get_forecast_engine()
        self.optimizer = optimizer or get_schedule_optimizer()
        self.settings = get_settings()

    def _ingest_weather(
        self, plants_cfg: List[Dict[str, Any]], target_date: date, db: Session
    ) -> Dict[str, Dict[int, Dict[str, float]]]:
        """
        Fetch, validate, resample, persist weather forecasts and format for feature builder.
        Returns mapping: plant_id -> {block_no -> {feature_name: value}}
        """
        weather_by_plant: Dict[str, Dict[int, Dict[str, float]]] = {}
        issue_time = datetime.now(timezone.utc)
        target_date_str = target_date.strftime("%Y-%m-%d")

        for plant in plants_cfg:
            plant_id = str(plant.get("id"))
            lat = plant.get("lat")
            lon = plant.get("lon")
            asset_type = str(plant.get("type", "solar")).lower()

            if lat is None or lon is None:
                logger.warning(f"Skipping weather ingestion for {plant_id}: missing coordinates.")
                continue

            try:
                raw_df = _run_async(fetch_weather_forecast(lat=float(lat), lon=float(lon), forecast_days=3))
            except Exception as exc:
                logger.warning(f"Failed to fetch Open-Meteo weather for plant {plant_id}: {exc}")
                raw_df = pd.DataFrame()

            if raw_df is None or raw_df.empty:
                logger.info(f"No weather data available for plant {plant_id}; continuing without live weather.")
                weather_by_plant[plant_id] = {}
                continue

            # Quality validation and cleaning
            cleaned_df, _ = validate_weather_data(raw_df)
            if asset_type == "solar":
                cleaned_df = zero_fill_nighttime_solar(cleaned_df)

            # 15-minute grid block alignment
            resampled_df = resample_hourly_to_15min(cleaned_df, time_col="timestamp")
            resampled_df = add_block_numbers(resampled_df, time_col="timestamp")
            resampled_df = add_ist_columns(resampled_df, utc_col="timestamp")

            # Filter for target date in IST/UTC context
            # We match the 96 blocks for target date
            plant_blocks_weather: Dict[int, Dict[str, float]] = {}

            # Filter rows for target date
            resampled_df["date_str"] = resampled_df["timestamp"].dt.strftime("%Y-%m-%d")
            day_df = resampled_df[resampled_df["date_str"] == target_date_str]
            if day_df.empty:
                # If target date isn't exact UTC date match, take first 96 blocks available
                day_df = resampled_df.head(96)

            for _, row in day_df.iterrows():
                block_no = int(row.get("block_no", 1))
                valid_dt = row["timestamp"].to_pydatetime()
                if valid_dt.tzinfo is None:
                    valid_dt = valid_dt.replace(tzinfo=timezone.utc)

                # Persist to WeatherForecast table
                wf_record = WeatherForecast(
                    plant_id=plant_id,
                    issue_time=issue_time,
                    valid_time=valid_dt,
                    ghi_w_m2=float(row["shortwave_radiation"]) if "shortwave_radiation" in row and pd.notna(row["shortwave_radiation"]) else None,
                    dni_w_m2=float(row["direct_normal_irradiance"]) if "direct_normal_irradiance" in row and pd.notna(row["direct_normal_irradiance"]) else None,
                    dhi_w_m2=float(row["diffuse_radiation"]) if "diffuse_radiation" in row and pd.notna(row["diffuse_radiation"]) else None,
                    wind_10m=float(row["wind_speed_10m"]) if "wind_speed_10m" in row and pd.notna(row["wind_speed_10m"]) else None,
                    wind_80m=float(row["wind_speed_80m"]) if "wind_speed_80m" in row and pd.notna(row["wind_speed_80m"]) else None,
                    wind_120m=float(row["wind_speed_120m"]) if "wind_speed_120m" in row and pd.notna(row["wind_speed_120m"]) else None,
                    temp_c=float(row["temperature_2m"]) if "temperature_2m" in row and pd.notna(row["temperature_2m"]) else None,
                    humidity_pct=float(row["relative_humidity_2m"]) if "relative_humidity_2m" in row and pd.notna(row["relative_humidity_2m"]) else None,
                    cloud_cover=float(row["cloud_cover"]) if "cloud_cover" in row and pd.notna(row["cloud_cover"]) else None,
                    source="open-meteo",
                )
                db.add(wf_record)

                # Weather feature dict for feature_builder / LGBM
                feature_vals = {}
                for col in row.index:
                    if pd.notna(row[col]) and isinstance(row[col], (int, float, np.number)):
                        feature_vals[col] = float(row[col])
                plant_blocks_weather[block_no] = feature_vals

            weather_by_plant[plant_id] = plant_blocks_weather

        db.flush()
        return weather_by_plant

    def run_pipeline(
        self, db: Session, target_date: Optional[date] = None, run_id: Optional[str] = None
    ) -> JobRun:
        if target_date is None:
            target_date = date.today()

        if run_id is None:
            run_id = str(uuid.uuid4())
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
        else:
            job_run = db.execute(select(JobRun).where(JobRun.id == run_id)).scalar_one_or_none()
            if job_run:
                job_run.status = "running"
                db.commit()
            else:
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

        date_str = target_date.strftime("%Y-%m-%d")
        start_time = time.time()

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

            # Step 0: Ingest & validate live weather forecasts
            weather_by_plant = self._ingest_weather(plants_cfg=plants_cfg, target_date=target_date, db=db)

            all_forecasts_by_plant: dict[str, list[dict]] = {}
            all_schedules_by_plant: dict[str, list[float]] = {}
            all_plants_meta: dict[str, dict] = {}

            for plant in plants_cfg:
                plant_id = plant["id"]
                asset_type = plant.get("type", "solar")
                avc_mw = float(plant.get("avc_mw", 50.0))
                all_plants_meta[plant_id] = plant

                forecast_blocks = self.forecast_engine.generate_forecast(
                    plant=plant,
                    date_str=date_str,
                    num_blocks=96,
                    weather=weather_by_plant.get(plant_id),
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
