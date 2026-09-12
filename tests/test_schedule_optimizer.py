"""Min-rupee schedule optimiser.

The invariant that matters most is the first one: optimising must never produce
a schedule that costs more than simply declaring P50. An optimiser that can lose
money is worse than no optimiser, because the dashboard presents its output as
a saving.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.modules.dsm.engine import DSMEngine
from backend.modules.forecast.mock_engine import MockForecastEngine
from backend.modules.optimize.schedule_optimizer import (
    QUANTILE_LEVELS,
    ProductionScheduleOptimizer,
    expected_penalty,
    quantile_weights,
)

AVC = 50.0
NCD = 450.0
FREQ = 50.0


@pytest.fixture()
def engine():
    return DSMEngine(config_path="config/dsm_rules_2026.yaml", rule_date=date(2026, 9, 13))


@pytest.fixture()
def blocks():
    plant = {"plant_id": "GJ_SOLAR_A", "avc_mw": AVC, "asset_type": "solar"}
    return MockForecastEngine().generate_forecast(plant, "2026-09-13", 96)


@pytest.fixture()
def result(engine, blocks):
    return ProductionScheduleOptimizer().optimize_day_ahead(
        blocks, avc_mw=AVC, dsm_engine=engine, ncd=NCD, freq_hz=FREQ, asset_type="solar"
    )


# ------------------------------------------------------------ quantile weights
def test_weights_sum_to_one():
    assert sum(quantile_weights().values()) == pytest.approx(1.0)


def test_central_quantiles_outweigh_the_tails():
    """P50 covers far more probability mass than P05. Uniform weighting -- what
    DSMEngine.compute_expected_penalty does -- inflates the tails and makes the
    optimiser over-conservative."""
    w = quantile_weights()
    assert w[0.50] > w[0.25] > w[0.05]
    assert w[0.05] == pytest.approx(w[0.95])


def test_weights_are_symmetric():
    w = quantile_weights()
    for low, high in ((0.05, 0.95), (0.10, 0.90), (0.25, 0.75)):
        assert w[low] == pytest.approx(w[high])


# -------------------------------------------------------------------- contract
def test_returns_every_key_the_dashboard_reads(result):
    for key in (
        "optimised_schedule", "naive_schedule", "battery_dispatch",
        "naive_total_inr", "optimised_total_inr", "savings_inr",
        "savings_pct", "action_cards",
    ):
        assert key in result, key


def test_schedules_cover_all_96_blocks(result):
    assert len(result["optimised_schedule"]) == 96
    assert len(result["naive_schedule"]) == 96


def test_battery_is_reported_as_not_modelled(result):
    """Zeros must not be mistakable for 'the optimiser chose not to dispatch'."""
    assert result["battery_modelled"] is False
    assert all(b["charge_mw"] == 0.0 and b["discharge_mw"] == 0.0
               for b in result["battery_dispatch"])


# ------------------------------------------------------------------ invariants
def test_optimising_is_never_worse_than_declaring_p50(result):
    """The one that must never regress."""
    assert result["optimised_total_inr"] <= result["naive_total_inr"] + 1e-6
    assert result["savings_inr"] >= -1e-6
    assert result["savings_pct"] >= -1e-6


def test_schedules_are_physically_declarable(result):
    assert all(0.0 <= mw <= AVC + 1e-6 for mw in result["optimised_schedule"])


def test_it_actually_finds_a_saving(result):
    """A realistic forecast band must leave something on the table to recover.

    If this fails with zero savings, suspect the forecast spread: a band
    narrower than the CERC tolerance band produces no penalties at all and the
    optimiser has nothing to optimise.
    """
    assert result["naive_total_inr"] > 0, "no penalty to optimise -- check forecast spread"
    assert result["savings_inr"] > 0
    assert result["savings_pct"] > 1.0


def test_beats_the_coarse_five_candidate_search(engine, blocks, result):
    from backend.modules.optimize.mock_optimizer import MockScheduleOptimizer

    coarse = MockScheduleOptimizer().optimize_day_ahead(
        blocks, avc_mw=AVC, dsm_engine=engine, ncd=NCD, freq_hz=FREQ, asset_type="solar"
    )

    def cost(schedule):
        total = 0.0
        for block, mw in zip(blocks, schedule):
            quantiles = {lvl: block[f"p{int(lvl * 100):02d}"] for lvl in QUANTILE_LEVELS}
            total += expected_penalty(engine, quantiles, mw, AVC, FREQ, NCD, "solar")
        return total

    assert cost(result["optimised_schedule"]) < cost(coarse["optimised_schedule"])


# ---------------------------------------------------------------- action cards
def test_action_cards_each_carry_a_rupee_impact(result):
    for card in result["action_cards"]:
        assert card["inr_impact"] > 0
        assert card["type"] in {"curtailment", "reserve_flag", "high_risk_block"}
        assert card["reason"]
        assert 1 <= card["block_no"] <= 96


def test_action_cards_are_ranked_by_money(result):
    impacts = [c["inr_impact"] for c in result["action_cards"]]
    assert impacts == sorted(impacts, reverse=True)


# ----------------------------------------------------------------- edge cases
def test_zero_capacity_plant_does_not_crash(engine, blocks):
    out = ProductionScheduleOptimizer().optimize_day_ahead(
        blocks, avc_mw=0.0, dsm_engine=engine, ncd=NCD, freq_hz=FREQ, asset_type="solar"
    )
    assert len(out["optimised_schedule"]) == 96
    assert all(mw == 0.0 for mw in out["optimised_schedule"])


def test_empty_forecast_returns_empty_not_an_error(engine):
    out = ProductionScheduleOptimizer().optimize_day_ahead(
        [], avc_mw=AVC, dsm_engine=engine, ncd=NCD, freq_hz=FREQ, asset_type="solar"
    )
    assert out["optimised_schedule"] == []
    assert out["savings_pct"] == 0.0


def test_block_without_quantiles_is_rejected(engine):
    with pytest.raises(ValueError):
        ProductionScheduleOptimizer().optimize_day_ahead(
            [{"block_no": 1}], avc_mw=AVC, dsm_engine=engine,
            ncd=NCD, freq_hz=FREQ, asset_type="solar",
        )


def test_wind_uses_its_wider_tolerance_band(engine):
    plant = {"plant_id": "GJ_WIND_C", "avc_mw": 60.0, "asset_type": "wind"}
    wind_blocks = MockForecastEngine().generate_forecast(plant, "2026-09-13", 96)
    out = ProductionScheduleOptimizer().optimize_day_ahead(
        wind_blocks, avc_mw=60.0, dsm_engine=engine, ncd=NCD, freq_hz=FREQ, asset_type="wind"
    )
    assert out["optimised_total_inr"] <= out["naive_total_inr"] + 1e-6


# ------------------------------------------------- the forecast-spread guard
def test_mock_forecast_band_is_wider_than_the_tolerance_band(blocks, engine):
    """Regression guard for the bug that made the whole demo read zero.

    The mock's P05-P95 band was +/-9% while the CERC solar tolerance band is
    +/-10%, so the entire forecast fell inside the no-penalty zone: every block
    scored zero, and the dashboard reported "saves Rs 0 (0.0%)".
    """
    peak = max(blocks, key=lambda b: b["p50"])
    assert peak["p50"] > 0
    half_width = (peak["p95"] - peak["p05"]) / 2.0 / peak["p50"]
    assert half_width > engine.solar_band, (
        f"forecast band +/-{half_width:.1%} is inside the CERC tolerance band "
        f"+/-{engine.solar_band:.0%}; no block can ever incur a penalty"
    )
