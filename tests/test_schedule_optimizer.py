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


# -------------------------------------------------------------- battery storage
from backend.modules.optimize.battery_recourse import (  # noqa: E402
    DT_HOURS,
    DEFAULT_EFFICIENCY,
    allowed_deviation_mw,
    block_with_battery,
)

BATTERY_MWH = AVC  # one hour of plant capacity


@pytest.fixture()
def battery_result(engine, blocks):
    return ProductionScheduleOptimizer().optimize_day_ahead(
        blocks, avc_mw=AVC, dsm_engine=engine, ncd=NCD, freq_hz=FREQ,
        asset_type="solar", battery_capacity_mwh=BATTERY_MWH,
    )


def test_a_fixed_battery_plan_is_the_same_as_declaring_a_different_schedule(engine):
    """Why the old day-ahead battery LP saved nothing at any size.

    With X = 1 a DSM penalty depends only on actual - schedule. Shifting every
    outcome by s is therefore identical to declaring schedule - s, which the
    schedule search already covers.
    """
    assert engine.x == pytest.approx(1.0)
    quantiles = {0.05: 18.0, 0.25: 24.0, 0.50: 30.0, 0.75: 36.0, 0.95: 44.0}
    for shift in (-6.0, -2.5, 3.0, 5.0):
        shifted = {q: v + shift for q, v in quantiles.items()}
        for schedule in (20.0, 30.0, 38.0):
            assert expected_penalty(engine, shifted, schedule, AVC, FREQ, NCD, "solar") == pytest.approx(
                expected_penalty(engine, quantiles, schedule - shift, AVC, FREQ, NCD, "solar")
            )


def test_the_battery_is_reported_as_modelled_when_requested(battery_result):
    assert battery_result["battery_modelled"] is True
    assert "battery_recourse" in battery_result["method"]


def test_a_battery_never_increases_the_expected_penalty(result, battery_result):
    """The guarantee: a correction only moves deviation toward the band."""
    assert battery_result["optimised_total_inr"] <= result["optimised_total_inr"] + 1e-6
    assert battery_result["optimised_without_battery_inr"] == pytest.approx(result["optimised_total_inr"])
    assert battery_result["battery_saving_inr"] >= 0.0


def test_a_battery_changes_the_rupee_figure(result, battery_result):
    """The regression this change exists for: the old LP dispatched hundreds of
    MWh and left optimised_total_inr identical at every battery size."""
    assert battery_result["optimised_total_inr"] < result["optimised_total_inr"] - 1.0
    assert battery_result["battery_saving_inr"] > 1.0


def test_totals_reconcile(battery_result):
    r = battery_result
    assert r["savings_inr"] == pytest.approx(r["naive_total_inr"] - r["optimised_total_inr"])
    assert r["battery_saving_inr"] == pytest.approx(
        r["optimised_without_battery_inr"] - r["optimised_total_inr"]
    )


def test_dispatch_respects_power_and_energy_limits(battery_result):
    power = BATTERY_MWH / 2.0
    for row in battery_result["battery_dispatch"]:
        assert 0.0 <= row["charge_mw"] <= power + 1e-6
        assert 0.0 <= row["discharge_mw"] <= power + 1e-6
        assert -1e-6 <= row["soc_mwh"] <= BATTERY_MWH + 1e-6


def test_state_of_charge_moves_no_faster_than_the_battery_can(battery_result):
    """Reported state of charge is the probability-weighted average of the scenario
    paths, so it cannot be replayed from the expected dispatch -- but no path can
    move faster than full power for one block."""
    power = BATTERY_MWH / 2.0
    max_step = DT_HOURS * max(DEFAULT_EFFICIENCY * power, power / DEFAULT_EFFICIENCY)
    previous = 0.5 * BATTERY_MWH
    for row in battery_result["battery_dispatch"]:
        assert abs(row["soc_mwh"] - previous) <= max_step + 1e-6
        previous = row["soc_mwh"]


def test_a_sustained_shortfall_drains_the_battery_instead_of_being_covered_all_day(engine):
    """The artefact this model exists to prevent.

    A draft that tracked one expected state of charge let the battery absorb the
    high outcomes and cover the low ones in the same block; in expectation they
    cancelled, the battery never emptied, and a half-hour battery 'eliminated'
    100% of a day's penalty. A real day that runs below forecast drains it.
    """
    from backend.modules.optimize.battery_recourse import optimise_with_battery

    # Every block wants 30 MW, and the low path delivers only 5 -- a shortfall far
    # outside the band, every block, all day.
    day = [
        {"block_no": i + 1, "p05": 5.0, "p10": 5.0, "p25": 30.0, "p50": 30.0,
         "p75": 30.0, "p90": 30.0, "p95": 30.0}
        for i in range(96)
    ]
    out = optimise_with_battery(day, avc_mw=AVC, dsm_engine=engine, capacity_mwh=12.5,
                                ncd=NCD, freq_hz=FREQ, asset_type="solar")
    late = [row["battery_saving_inr"] for row in out["per_block"][48:]]
    early = [row["battery_saving_inr"] for row in out["per_block"][:4]]
    assert max(early) > 0, "a charged battery should help at the start of the day"
    assert max(late) == pytest.approx(0.0, abs=1e-6), "an emptied battery cannot keep helping"


def test_storage_cards_carry_only_the_battery_share(battery_result):
    """Card rupees must not add up to more than was actually saved."""
    storage = [c for c in battery_result["action_cards"] if c["type"] == "storage_dispatch"]
    assert storage, "a modelled battery that saves money should recommend dispatch"
    for card in storage:
        assert card["inr_impact"] > 0
    assert sum(c["inr_impact"] for c in battery_result["action_cards"] if c["type"] != "high_risk_block") \
        <= battery_result["savings_inr"] + 1e-6


def test_no_battery_still_reports_zero_dispatch_and_no_storage_cards(result):
    assert result["battery_saving_inr"] == 0.0
    assert not any(c["type"] == "storage_dispatch" for c in result["action_cards"])


# ----------------------------------------------------- the single-block response
def _one(engine, actual, schedule, avc=100.0, freq=FREQ, charge_room=100.0, discharge_room=100.0):
    return block_with_battery(
        engine, {0.5: actual}, {0.5: 1.0}, schedule, avc, freq, NCD, "solar",
        charge_room, discharge_room,
    )


def test_an_over_injection_is_absorbed_back_into_the_band(engine):
    limit = allowed_deviation_mw(engine, 40.0, 100.0, "solar")
    out = _one(engine, actual=70.0, schedule=40.0)
    assert out["without"] > 0
    assert out["with"] == 0.0
    assert out["charge"] == pytest.approx(30.0 - limit, rel=1e-6)


def test_a_shortfall_is_covered_back_into_the_band(engine):
    out = _one(engine, actual=20.0, schedule=50.0)
    assert out["without"] > 0 and out["with"] == 0.0
    assert out["discharge"] > 0 and out["charge"] == 0.0


def test_a_power_limited_battery_still_reduces_the_charge(engine):
    """Beyond the band the charge is linear in the deviation, so a partial
    correction is worth money even when it cannot reach the band."""
    out = _one(engine, actual=70.0, schedule=40.0, charge_room=5.0)
    assert out["charge"] == pytest.approx(5.0)
    assert 0 < out["with"] < out["without"]


def test_an_empty_battery_does_nothing(engine):
    out = _one(engine, actual=20.0, schedule=50.0, discharge_room=0.0)
    assert out["discharge"] == 0.0 and out["with"] == out["without"]


def test_a_deviation_inside_the_band_spends_no_energy(engine):
    out = _one(engine, actual=45.0, schedule=40.0)
    assert out["without"] == 0.0 and out["charge"] == 0.0 and out["discharge"] == 0.0


def test_unpriced_over_injection_at_high_frequency_is_not_absorbed(engine):
    """Over-injection at >= 50.05 Hz carries no charge; absorbing it would drain
    the battery for nothing."""
    out = _one(engine, actual=70.0, schedule=40.0, freq=50.1)
    assert out["without"] == 0.0 and out["charge"] == 0.0


def test_a_correction_never_flips_the_direction_of_deviation(engine):
    out = _one(engine, actual=70.0, schedule=40.0)
    assert 70.0 - out["charge"] > 40.0
