"""Build the exact 61-feature frame the LightGBM boosters were trained on.

The feature order is not negotiable: LightGBM matches features positionally, so
a frame in the wrong order predicts confidently and wrongly. The canonical order
is read from the model file itself at load time (`booster.feature_name()`), not
copied into this module, so the two can never drift.

On missing values
-----------------
Anything genuinely unknown is left as NaN rather than filled with zero.
LightGBM learned a default split direction for missing values during training,
so NaN means "unknown" to the model, while 0.0 means "this quantity really is
zero" -- a very different claim. Filling zeros here would be silent fabrication
of exactly the kind this codebase is otherwise careful to prevent.

Three of the 61 features cannot exist for a genuine future forecast:

    DC_POWER, DAILY_YIELD, TOTAL_YIELD

They are measured at the same instant as the AC_POWER target, so at forecast
issue time for a future block they are unknowable. DC_POWER alone carries ~25%
of total model gain. They are always NaN here, and `completeness()` reports the
resulting degradation so a caller can refuse to serve rather than quietly ship a
weakened forecast. The real fix is retraining without them; see
docs/model_integration.md.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np

# Measured simultaneously with the target. Never available for a future block.
LEAKING_FEATURES = ("DC_POWER", "DAILY_YIELD", "TOTAL_YIELD")

# Weather variables Open-Meteo supplies, matching the training column names.
WEATHER_FEATURES = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "direct_normal_irradiance",
    "global_tilted_irradiance",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
    "precipitation",
)

BLOCK_MINUTES = 15
IST = timezone(timedelta(hours=5, minutes=30))


def block_timestamps(date_str: str, num_blocks: int) -> list[datetime]:
    """The IST wall-clock instant each 15-minute block starts at.

    Block 1 is 00:00-00:15 IST. Indian scheduling is defined in IST, and the
    training data's `hour`/`is_daytime` columns follow local time, so building
    these in UTC would shift the solar profile by 5h30m.
    """
    start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=IST)
    return [start + timedelta(minutes=BLOCK_MINUTES * (i - 1)) for i in range(1, num_blocks + 1)]


def _time_features(ts: datetime) -> dict[str, float]:
    day_of_year = ts.timetuple().tm_yday
    return {
        "hour": float(ts.hour),
        "minute": float(ts.minute),
        "day": float(ts.day),
        "month": float(ts.month),
        "day_of_week": float(ts.weekday()),
        "day_of_year": float(day_of_year),
        "hour_sin": math.sin(2 * math.pi * ts.hour / 24.0),
        "hour_cos": math.cos(2 * math.pi * ts.hour / 24.0),
        "day_sin": math.sin(2 * math.pi * day_of_year / 365.0),
        "day_cos": math.cos(2 * math.pi * day_of_year / 365.0),
        # Daylight is approximated by hour-of-day rather than solar geometry.
        # The models use it as a coarse gate, not a physical irradiance term.
        "is_daytime": 1.0 if 6 <= ts.hour < 19 else 0.0,
    }


def build_frame(
    feature_order: list[str],
    date_str: str,
    num_blocks: int,
    *,
    weather: dict[int, dict] | None = None,
    history: dict[str, float] | None = None,
) -> np.ndarray:
    """Assemble an (num_blocks, len(feature_order)) float array.

    weather -- {block_no: {open_meteo_variable: value}}, optional.
    history -- precomputed generation lag/rolling features, optional.

    Unknown values are NaN by design; see the module docstring.
    """
    weather = weather or {}
    history = history or {}
    timestamps = block_timestamps(date_str, num_blocks)

    index = {name: i for i, name in enumerate(feature_order)}
    frame = np.full((num_blocks, len(feature_order)), np.nan, dtype=np.float64)

    for row, ts in enumerate(timestamps):
        block_no = row + 1
        values: dict[str, float] = {}
        values.update(_time_features(ts))

        block_weather = weather.get(block_no, {})
        for name in WEATHER_FEATURES:
            if name in block_weather and block_weather[name] is not None:
                values[name] = float(block_weather[name])
                # The *_lag1 variants are the previous block's reading.
                prev = weather.get(block_no - 1, {})
                if name in prev and prev[name] is not None:
                    values[f"{name}_lag1"] = float(prev[name])

        for name, value in history.items():
            if value is not None:
                values[name] = float(value)

        for name, value in values.items():
            position = index.get(name)
            if position is not None:
                frame[row, position] = value

    return frame


def completeness(feature_order: list[str], frame: np.ndarray) -> dict:
    """How much of the feature space is actually populated.

    Returned alongside every forecast so a degraded one is visible rather than
    merely plausible. `unavailable_by_design` counts the three leaking features,
    which can never be filled for a future block and so are not a data-quality
    failure -- they are a model-design problem.
    """
    total = frame.size
    present = int(np.count_nonzero(~np.isnan(frame)))
    missing_names = [
        name
        for i, name in enumerate(feature_order)
        if bool(np.all(np.isnan(frame[:, i])))
    ]
    return {
        "populated_pct": round(100.0 * present / total, 1) if total else 0.0,
        "features_total": len(feature_order),
        "features_all_missing": len(missing_names),
        "unavailable_by_design": [n for n in missing_names if n in LEAKING_FEATURES],
        "missing": missing_names,
    }
