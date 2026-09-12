"""Block numbering must agree between the weather pipeline and the model input.

CERC settles in 96 blocks of 15 minutes with block 1 = 00:00-00:15 **IST**.
Two independent places compute that:

  - backend.data.quality.resampler.add_block_numbers, over Open-Meteo's UTC frame
  - backend.modules.forecast.feature_builder.block_timestamps, for model features

They used to disagree by 5h30m (22 blocks), because the resampler derived the
block from the UTC hour. Weather sampled at dawn was handed to the model as
midnight. These tests pin them together.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backend.data.quality.resampler import add_block_numbers, resample_hourly_to_15min
from backend.modules.forecast import feature_builder


def _utc_frame(start="2026-09-13 00:00", periods=96):
    return pd.DataFrame({"timestamp": pd.date_range(start, periods=periods, freq="15min", tz="UTC")})


def test_block_one_is_midnight_ist_not_midnight_utc():
    """00:00 UTC is 05:30 IST, which is block 23 -- not block 1."""
    df = add_block_numbers(_utc_frame())
    first = df.iloc[0]
    assert first["ist_time"] == "05:30"
    assert int(first["block_no"]) == 23, "00:00 UTC must not be block 1"


def test_midnight_ist_is_block_one():
    # 18:30 UTC on the previous day is 00:00 IST.
    df = add_block_numbers(_utc_frame(start="2026-09-12 18:30", periods=4))
    assert df.iloc[0]["ist_time"] == "00:00"
    assert int(df.iloc[0]["block_no"]) == 1


def test_resampler_and_feature_builder_agree():
    """The regression guard. Both must place a given IST instant in the same block."""
    df = add_block_numbers(_utc_frame(start="2026-09-12 18:30", periods=96))
    builder_blocks = feature_builder.block_timestamps("2026-09-13", 96)

    for i in range(0, 96, 7):
        resampler_block = int(df.iloc[i]["block_no"])
        resampler_ist = df.iloc[i]["ist_time"]
        builder_ist = builder_blocks[resampler_block - 1].strftime("%H:%M")
        assert resampler_ist == builder_ist, (
            f"block {resampler_block}: resampler says {resampler_ist} IST, "
            f"feature_builder says {builder_ist} IST"
        )


def test_block_numbers_span_one_to_96():
    df = add_block_numbers(_utc_frame(start="2026-09-12 18:30", periods=96))
    assert sorted(df["block_no"].unique()) == list(range(1, 97))


@pytest.mark.parametrize(
    "ist_clock,expected_block",
    [("00:00", 1), ("00:15", 2), ("06:00", 25), ("12:00", 49), ("23:45", 96)],
)
def test_known_ist_times_map_to_known_blocks(ist_clock, expected_block):
    utc_start = pd.Timestamp("2026-09-12 18:30", tz="UTC")
    df = add_block_numbers(pd.DataFrame({"timestamp": pd.date_range(utc_start, periods=96, freq="15min")}))
    row = df[df["ist_time"] == ist_clock].iloc[0]
    assert int(row["block_no"]) == expected_block


def test_missing_time_column_is_a_no_op():
    df = pd.DataFrame({"other": [1, 2]})
    assert add_block_numbers(df).equals(df)


def test_resample_then_block_number_keeps_alignment():
    """The real pipeline order: Open-Meteo hourly -> 15-min -> block numbers."""
    hourly = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-12 18:30", periods=6, freq="h", tz="UTC"),
        "shortwave_radiation": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    })
    out = add_block_numbers(resample_hourly_to_15min(hourly))
    assert int(out.iloc[0]["block_no"]) == 1
    assert out.iloc[0]["ist_time"] == "00:00"
