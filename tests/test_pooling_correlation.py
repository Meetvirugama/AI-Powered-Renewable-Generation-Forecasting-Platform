"""Portfolio pooling: the correlation model that makes diversification real.

The bug these guard against: pooled quantiles were built by summing the same
quantile level across plants, which asserts every plant hits its 5th percentile
in the same block. That is perfect correlation -- the one case where pooling
cannot help -- and it made pooling measurably *harmful* (-11.5% on the four
configured plants) against a README promising a 30-65% reduction.
"""
from __future__ import annotations

import importlib
from datetime import date

import pytest

from backend.modules.dsm import pooling as pooling_module
from backend.modules.dsm.engine import DSMEngine

LEVELS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


@pytest.fixture()
def engine():
    return DSMEngine(config_path="config/dsm_rules_2026.yaml", rule_date=date(2026, 9, 13))


def _fan(p50: float, spread: float) -> dict[float, float]:
    """A symmetric quantile fan around p50, spread expressed as a fraction."""
    return {lvl: max(0.0, p50 * (1 + spread * (lvl - 0.5))) for lvl in LEVELS}


def _plant(plant_id: str, p50: float, avc: float, asset_type: str = "solar",
           schedule: float | None = None, spread: float = 0.8) -> dict:
    return {
        "plant_id": plant_id,
        "asset_type": asset_type,
        "avc_mw": avc,
        "schedule_mw": p50 if schedule is None else schedule,
        "quantile_forecasts": _fan(p50, spread),
    }


def _reload_with(monkeypatch, same: float, cross: float):
    monkeypatch.setenv("POOL_CORRELATION_SAME_TYPE", str(same))
    monkeypatch.setenv("POOL_CORRELATION_CROSS_TYPE", str(cross))
    return importlib.reload(pooling_module)


# --------------------------------------------------------------- the maths
def test_medians_add_exactly():
    """Expectations are additive whatever the correlation -- only spread changes."""
    plants = [_plant("A", 40.0, 50.0), _plant("B", 60.0, 75.0)]
    pooled = pooling_module.pool_quantiles(plants)
    assert pooled[0.50] == pytest.approx(100.0)


def test_perfect_correlation_reproduces_plain_summation(monkeypatch):
    """rho = 1 must collapse to the old behaviour exactly.

    This is the correctness anchor: a variance-addition model that does not
    reduce to simple summation at rho = 1 is wrong.
    """
    mod = _reload_with(monkeypatch, 1.0, 1.0)
    plants = [_plant("A", 40.0, 50.0), _plant("B", 60.0, 75.0)]
    pooled = mod.pool_quantiles(plants)

    for level in LEVELS:
        naive = sum(p["quantile_forecasts"][level] for p in plants)
        assert pooled[level] == pytest.approx(naive, rel=1e-9)


def test_independence_shrinks_the_band(monkeypatch):
    """rho = 0 must narrow the pooled fan relative to naive summation."""
    mod = _reload_with(monkeypatch, 0.0, 0.0)
    plants = [_plant("A", 50.0, 50.0), _plant("B", 50.0, 50.0)]
    pooled = mod.pool_quantiles(plants)

    naive_p05 = sum(p["quantile_forecasts"][0.05] for p in plants)
    assert pooled[0.05] > naive_p05, "independent plants should have a tighter lower tail"

    # Two identical independent plants: spread grows as sqrt(2), not 2.
    single_dev = 50.0 - _fan(50.0, 0.8)[0.05]
    pooled_dev = pooled[0.50] - pooled[0.05]
    assert pooled_dev == pytest.approx(single_dev * (2 ** 0.5), rel=1e-6)


def test_lower_correlation_means_more_benefit(engine, monkeypatch):
    """Monotonicity: the less correlated the pool, the more it saves."""
    savings = []
    for rho in (0.9, 0.6, 0.3, 0.0):
        mod = _reload_with(monkeypatch, rho, rho)
        plants = [_plant("A", 40.0, 50.0), _plant("B", 45.0, 50.0), _plant("C", 38.0, 50.0)]
        result = mod.compute_pooling_benefit(plants, engine, 450.0, 50.0)
        savings.append(result["savings_pct"])

    assert savings == sorted(savings), f"benefit should rise as correlation falls: {savings}"


# ------------------------------------------------------------- the regression
def test_a_diversified_pool_is_beneficial_not_harmful(engine, monkeypatch):
    """The headline regression. Pooling must not cost money."""
    mod = _reload_with(monkeypatch, 0.70, 0.15)
    plants = [
        _plant("GJ_SOLAR_A", 40.0, 50.0, "solar"),
        _plant("GJ_SOLAR_B", 55.0, 75.0, "solar"),
        _plant("GJ_WIND_C", 20.0, 40.0, "wind"),
    ]
    result = mod.compute_pooling_benefit(plants, engine, 450.0, 50.0)

    assert result["beneficial"] is True
    assert result["savings_inr"] > 0
    assert result["savings_pct"] > 0


def test_mixed_technology_pools_better_than_single_technology(engine, monkeypatch):
    """Solar and wind share less weather, so a mixed pool should diversify more."""
    mod = _reload_with(monkeypatch, 0.70, 0.15)

    all_solar = [_plant(f"S{i}", 40.0, 50.0, "solar") for i in range(3)]
    mixed = [
        _plant("S1", 40.0, 50.0, "solar"),
        _plant("S2", 40.0, 50.0, "solar"),
        _plant("W1", 40.0, 50.0, "wind"),
    ]

    solar_pct = mod.compute_pooling_benefit(all_solar, engine, 450.0, 50.0)["savings_pct"]
    mixed_pct = mod.compute_pooling_benefit(mixed, engine, 450.0, 50.0)["savings_pct"]
    assert mixed_pct > solar_pct


# ----------------------------------------------------------------- contract
def test_result_declares_its_assumptions(engine):
    """The correlation is an assumption, not a measurement -- it must be visible."""
    plants = [_plant("A", 40.0, 50.0), _plant("B", 45.0, 50.0)]
    result = pooling_module.compute_pooling_benefit(plants, engine, 450.0, 50.0)

    assert "correlation_assumed" in result
    assert 0.0 <= result["correlation_assumed"] <= 1.0
    assert result["pool_size"] == 2
    assert result["asset_type_used"] in {"solar", "wind"}


def test_keys_the_dashboard_and_pooling_route_read_are_preserved(engine):
    plants = [_plant("A", 40.0, 50.0), _plant("B", 45.0, 50.0)]
    result = pooling_module.compute_pooling_benefit(plants, engine, 450.0, 50.0)
    for key in ("individual_total_inr", "pooled_total_inr", "savings_inr",
                "savings_pct", "per_plant"):
        assert key in result, key


def test_dominant_asset_type_is_by_capacity_not_list_order(engine):
    """A 10 MW solar plant listed first must not set the band for 200 MW of wind."""
    plants = [
        _plant("small_solar", 8.0, 10.0, "solar"),
        _plant("big_wind", 150.0, 200.0, "wind"),
    ]
    result = pooling_module.compute_pooling_benefit(plants, engine, 450.0, 50.0)
    assert result["asset_type_used"] == "wind"


# ---------------------------------------------------------------- edge cases
def test_single_plant_pool_saves_nothing(engine):
    """There is nothing to diversify against."""
    result = pooling_module.compute_pooling_benefit(
        [_plant("solo", 40.0, 50.0)], engine, 450.0, 50.0
    )
    assert result["savings_inr"] == pytest.approx(0.0, abs=1e-6)
    assert result["beneficial"] is False


def test_empty_pool_returns_zeros_not_an_error(engine):
    result = pooling_module.compute_pooling_benefit([], engine, 450.0, 50.0)
    assert result["individual_total_inr"] == 0.0
    assert result["per_plant"] == []


def test_pool_quantiles_of_nothing_is_empty():
    assert pooling_module.pool_quantiles([]) == {}


def test_zero_spread_forecast_pools_to_zero_spread():
    """Certain forecasts stay certain however they are combined."""
    plants = [_plant("A", 40.0, 50.0, spread=0.0), _plant("B", 60.0, 50.0, spread=0.0)]
    pooled = pooling_module.pool_quantiles(plants)
    assert len(set(round(v, 6) for v in pooled.values())) == 1


def test_allocation_conserves_the_pooled_charge():
    """Every rupee of the pooled charge must be allocated to somebody."""
    individual = {"A": 300.0, "B": 700.0}
    allocated = pooling_module.allocate_pool_savings(individual, 600.0)
    assert sum(allocated.values()) == pytest.approx(600.0)
    assert allocated["B"] > allocated["A"], "more exposure should carry more cost"


def test_allocation_with_no_penalties_is_all_zero():
    assert pooling_module.allocate_pool_savings({"A": 0.0, "B": 0.0}, 0.0) == {"A": 0.0, "B": 0.0}


def test_realised_deviation_nets_without_any_correlation_model():
    """Actuals are known, so they simply net -- no assumption involved."""
    deviation = pooling_module.compute_pooled_deviation(
        plants_actual={"A": 45.0, "B": 35.0},      # +5 and -5 against schedule
        plants_schedule={"A": 40.0, "B": 40.0},
        pool_avc_mw=100.0,
        x=1.0,
    )
    assert deviation == pytest.approx(0.0), "opposite deviations must cancel exactly"


# ------------------------------------------------- per-block settlement guard
def test_passing_a_flattened_day_is_rejected(engine):
    """The bug that put a 100% pooling saving on the dashboard.

    Both API routes built one flat list of every (plant, block) pair and called
    compute_pooling_benefit once. That treats 288 plant-blocks as 288
    simultaneous plants, inflating pool AvC (and the tolerance band with it)
    96-fold until the pooled penalty is trivially zero.
    """
    flattened = [_plant("A", 40.0, 50.0), _plant("A", 42.0, 50.0), _plant("B", 30.0, 40.0)]
    with pytest.raises(ValueError) as exc:
        pooling_module.compute_pooling_benefit(flattened, engine, 450.0, 50.0)
    message = str(exc.value)
    assert "more than once" in message
    assert "compute_pooling_benefit_by_block" in message, "the error should name the fix"


def test_day_level_helper_sums_per_block_results(engine):
    block = [_plant("A", 40.0, 50.0), _plant("B", 55.0, 75.0)]
    single = pooling_module.compute_pooling_benefit(block, engine, 450.0, 50.0)
    day = pooling_module.compute_pooling_benefit_by_block([block] * 96, engine, 450.0, 50.0)

    assert day["blocks_settled"] == 96
    assert day["individual_total_inr"] == pytest.approx(single["individual_total_inr"] * 96)
    assert day["pooled_total_inr"] == pytest.approx(single["pooled_total_inr"] * 96)
    # The percentage is scale-invariant, so it must match the single block.
    assert day["savings_pct"] == pytest.approx(single["savings_pct"])


def test_day_level_helper_does_not_inflate_pool_capacity(engine):
    """pool_avc_mw must describe the pool, not the pool times 96 blocks."""
    block = [_plant("A", 40.0, 50.0), _plant("B", 55.0, 75.0)]
    day = pooling_module.compute_pooling_benefit_by_block([block] * 96, engine, 450.0, 50.0)
    assert day["pool_avc_mw"] == pytest.approx(125.0)


def test_day_level_helper_tolerates_empty_blocks(engine):
    block = [_plant("A", 40.0, 50.0), _plant("B", 55.0, 75.0)]
    day = pooling_module.compute_pooling_benefit_by_block([block, [], block], engine, 450.0, 50.0)
    assert day["blocks_settled"] == 2


def test_day_level_helper_on_no_blocks(engine):
    day = pooling_module.compute_pooling_benefit_by_block([], engine, 450.0, 50.0)
    assert day["individual_total_inr"] == 0.0
    assert day["savings_pct"] == 0.0


# ------------------------------------------------------ mixed-technology band
def test_a_mixed_pool_uses_a_capacity_weighted_band_not_the_dominant_one(engine):
    """A pool of 7 wind and 3 solar plants settled its solar output on the wider
    wind band and reported a 100% saving on the live data. Each plant's band now
    counts in proportion to its capacity."""
    plants = [
        _plant("solar", 30.0, 100.0, "solar"),
        _plant("wind", 30.0, 300.0, "wind"),
    ]
    result = pooling_module.compute_pooling_benefit(plants, engine, 450.0, 50.0)
    expected_band = (100.0 * engine.solar_band + 300.0 * engine.wind_band) / 400.0
    assert result["tolerance_band_used"] == pytest.approx(expected_band)
    assert engine.solar_band < result["tolerance_band_used"] < engine.wind_band
    assert result["asset_type_used"] == "wind"  # still reported, no longer applied


def test_a_single_technology_pool_keeps_its_own_band(engine):
    plants = [_plant("A", 40.0, 50.0, "solar"), _plant("B", 45.0, 60.0, "solar")]
    result = pooling_module.compute_pooling_benefit(plants, engine, 450.0, 50.0)
    assert result["tolerance_band_used"] == pytest.approx(engine.solar_band)


def test_the_day_level_helper_reports_the_band_it_used(engine):
    block = [_plant("A", 40.0, 50.0, "solar"), _plant("W", 20.0, 50.0, "wind")]
    result = pooling_module.compute_pooling_benefit_by_block([block, block], engine, 450.0, 50.0)
    assert result["tolerance_band_used"] == pytest.approx((engine.solar_band + engine.wind_band) / 2)
