"""Weather for a forecast request, shaped for the feature builder.

Why this exists
---------------
`LGBMForecastEngine` refuses to forecast without weather -- 33 of its 44
features come from Open-Meteo, and a frame without them is a day derived from
the calendar. But every API route called `generate_forecast()` with no weather
at all; only the nightly pipeline supplied any. So switching
`FORECAST_ENGINE_TYPE=production` would have turned all six forecast endpoints
into 500s.

The nightly pipeline persists weather to `weather_forecasts`, but that table
stores nine columns of a sixteen-variable feature set. Reading it back would
build a frame at roughly 61% completeness -- below the engine's floor, and
below what the models were trained on. So a request fetches Open-Meteo directly,
the same source the pipeline uses, and caches it.

Caching
-------
Open-Meteo updates hourly and is free, but a dashboard load fans out to several
endpoints for the same plant and date. The cache is per (plant, date), in
process, with a TTL well under the update interval. It is deliberately not
persisted: a stale forecast that survives a restart is harder to notice than a
slow one.

Failure
-------
On any failure this returns an empty mapping rather than partial or invented
weather. The engine then refuses, which surfaces as a clear error instead of a
forecast built from the clock.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from backend.data.ingestion.openmeteo import fetch_weather_forecast
from backend.modules.forecast import feature_builder

logger = logging.getLogger("renewable_platform")

# Open-Meteo publishes hourly. Holding a response for 15 minutes collapses the
# fan-out of a single dashboard load without ever serving yesterday's sky.
CACHE_TTL_SECONDS = float(os.getenv("WEATHER_CACHE_TTL_SECONDS", "900"))

_cache: dict[tuple[str, str], tuple[float, dict[int, dict[str, float]]]] = {}
_lock = threading.Lock()


def _run_async(coro):
    """Call an async fetcher from a sync request handler.

    FastAPI routes here are sync (`def`, not `async def`), so they run in a
    worker thread with no event loop of their own. `asyncio.run` is therefore
    safe -- but assert it, because being wrong means a deadlock under load
    rather than an exception in development.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    raise RuntimeError(
        "weather_provider was called from an async context; use the async path "
        "or move the call to a threadpool"
    )


def _fetch(lat: float, lon: float) -> pd.DataFrame:
    """The single point where this module talks to the network.

    Separated so the coroutine is built and awaited in one place -- creating it
    at the call site means a test that replaces the runner leaks an un-awaited
    coroutine, and it is the obvious seam to stub.
    """
    return _run_async(fetch_weather_forecast(lat=lat, lon=lon, forecast_days=3))


def _to_blocks(df: pd.DataFrame, date_str: str, num_blocks: int) -> dict[int, dict[str, float]]:
    """Resample an hourly Open-Meteo frame onto the 96 IST settlement blocks.

    Block 1 is 00:00 IST, so the day being asked about is not a UTC day. The
    timestamps are matched in UTC instants rather than by date string, which is
    what makes the 05:30 offset a non-issue.
    """
    if df is None or df.empty or "timestamp" not in df:
        return {}

    frame = df.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.set_index("timestamp").sort_index()

    numeric = frame.select_dtypes("number")
    if numeric.empty:
        return {}

    # Linear interpolation between hourly readings. Irradiance and temperature
    # both vary smoothly at this resolution; holding the hourly value flat
    # across four blocks would put a visible staircase in the forecast.
    targets = [
        ts.astimezone(timezone.utc)
        for ts in feature_builder.block_timestamps(date_str, num_blocks)
    ]
    union = numeric.index.union(pd.DatetimeIndex(targets))
    resampled = numeric.reindex(union).interpolate(method="time").reindex(targets)

    out: dict[int, dict[str, float]] = {}
    for row, ts in enumerate(targets):
        values = resampled.iloc[row]
        block = {
            name: float(values[name])
            for name in feature_builder.WEATHER_FEATURES
            if name in values and pd.notna(values[name])
        }
        if block:
            out[row + 1] = block
    return out


def _is_stale(date_str: str) -> bool:
    """Open-Meteo's free forecast endpoint reaches ~16 days ahead and holds only
    a few days of past data. Asking it for last month returns nothing useful."""
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    age = datetime.now(timezone.utc) - target
    return age > timedelta(days=2)


def weather_for(
    plant: dict, date_str: str, num_blocks: int = 96
) -> dict[int, dict[str, float]]:
    """Return {block_no: {variable: value}}, or {} if it could not be had.

    Never raises. An empty result is a truthful "no weather", which the engine
    turns into an explicit refusal; an exception here would instead surface as
    an opaque 500 on a dashboard load.
    """
    plant_id = str(plant.get("id") or plant.get("plant_id") or "?")
    lat, lon = plant.get("lat"), plant.get("lon")

    if lat is None or lon is None:
        logger.warning("no coordinates for plant %s; cannot fetch weather", plant_id)
        return {}

    key = (plant_id, date_str)
    now = time.monotonic()

    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

    if _is_stale(date_str):
        logger.info(
            "weather for %s on %s is outside Open-Meteo's forecast window", plant_id, date_str
        )
        return {}

    try:
        raw = _fetch(float(lat), float(lon))
        blocks = _to_blocks(raw, date_str, num_blocks)
    except Exception as exc:  # noqa: BLE001
        logger.warning("weather fetch failed for %s on %s: %s", plant_id, date_str, exc)
        return {}

    if not blocks:
        logger.warning("Open-Meteo returned no usable rows for %s on %s", plant_id, date_str)
        return {}

    with _lock:
        _cache[key] = (now, blocks)

    logger.info(
        "weather for %s on %s: %d blocks, %d variables",
        plant_id, date_str, len(blocks), len(next(iter(blocks.values()))),
    )
    return blocks


def clear_cache() -> None:
    """For tests, and for an operator who has just changed the plant config."""
    with _lock:
        _cache.clear()


def forecast_for(engine, plant: dict, date_str: str, num_blocks: int = 96) -> list[dict]:
    """Run `engine.generate_forecast`, supplying weather if the engine needs it.

    Every API route goes through here rather than calling the engine directly.
    Before it existed the routes passed no weather at all, which the mock engine
    ignores and the production engine cannot work without -- so
    `FORECAST_ENGINE_TYPE=production` produced a 500 on every forecast endpoint
    while the mock produced a plausible chart, and nothing in the response
    distinguished the two.
    """
    if not getattr(engine, "requires_weather", False):
        return engine.generate_forecast(plant=plant, date_str=date_str, num_blocks=num_blocks)

    return engine.generate_forecast(
        plant=plant,
        date_str=date_str,
        num_blocks=num_blocks,
        weather=weather_for(plant, date_str, num_blocks),
    )
