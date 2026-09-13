import math

from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

from backend.core.dates import validate_iso_date

# A DSM day is 96 settlement blocks of 15 minutes.
BLOCKS_PER_DAY = 96


class DSMRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    date: str
    schedule_mw: list[float] = []
    rule_year: Optional[int] = 2026
    freq_hz: Optional[float] = 50.0
    ncd_inr: Optional[float] = 450.0

    _date = field_validator("date")(validate_iso_date)

    @field_validator("schedule_mw")
    @classmethod
    def _one_declaration_per_block(cls, value: list[float]) -> list[float]:
        # A short schedule used to be padded with 0 MW for every missing block, so
        # a one-value schedule priced 95 blocks as "declared nothing" and returned
        # a large, confident penalty that no operator had ever declared.
        if len(value) != BLOCKS_PER_DAY:
            raise ValueError(
                f"schedule_mw must have exactly {BLOCKS_PER_DAY} values, one per 15-minute block; got {len(value)}"
            )
        if any(not math.isfinite(mw) or mw < 0 for mw in value):
            raise ValueError("schedule_mw values must be finite and non-negative")
        return value


class BlockDSMResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    block_no: int
    expected_penalty_inr: float
    p50_penalty_inr: float
    schedule_mw: float
    deviation_pct_at_p50: float


class DSMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plant_id: str
    date: str
    rule_version: str
    x_value: float
    total_expected_penalty_inr: float
    total_p50_penalty_inr: float
    blocks: list[BlockDSMResult]
