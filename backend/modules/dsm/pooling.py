"""Portfolio pooling: netting deviations across plants before they are settled.

Why pooling pays
----------------
Two plants that deviate in opposite directions in the same time block cancel.
Settled individually, both are charged; settled as a pool, only the *net*
deviation is. The entire benefit therefore comes from plants being imperfectly
correlated -- it is diversification, nothing else.

The bug this file used to carry
-------------------------------
The pooled quantile fan was built by summing the same quantile level across
plants:

    pooled_P05 = sum(P05_i)

which asserts that every plant hits its 5th percentile in the *same* block.
That is perfect correlation, the one case in which pooling cannot help at all.
Measured on the four configured plants it made pooling look actively harmful
(individual Rs 78,930/day vs pooled Rs 87,999/day, i.e. -11.5%) against a README
claiming a 30-65% reduction.

What it does now
----------------
Medians still add -- expectations are additive regardless of correlation. The
*spread* around the median is combined by variance addition instead:

    sigma_pool = sqrt( sum(sigma_i^2) + 2 * rho * sum_{i<j}(sigma_i * sigma_j) )

which is the standard result for a sum of correlated random variables, and
degrades correctly at both ends:

    rho = 1  ->  sigma_pool = sum(sigma_i)        (the old behaviour)
    rho = 0  ->  sigma_pool = sqrt(sum(sigma_i^2))  (independent: shrinks by ~sqrt(N))

Correlation is an assumption, not a measurement
-----------------------------------------------
Estimating rho properly needs concurrent generation history for every plant,
which this project does not have. Rather than hide that, the assumed values are
declared in the result (`correlation_assumed`) so the number can be reported
honestly and re-derived by anyone who disagrees with the defaults. Override via
POOL_CORRELATION_SAME_TYPE / POOL_CORRELATION_CROSS_TYPE.
"""
from __future__ import annotations

import math
import os
from typing import Dict, List

# Plants of the same technology in one state share a weather regime, so their
# output is strongly but not perfectly correlated. Solar and wind are driven by
# largely different physics and correlate weakly -- which is exactly why a mixed
# pool diversifies better than a single-technology one.
DEFAULT_RHO_SAME_TYPE = 0.70
DEFAULT_RHO_CROSS_TYPE = 0.15


def _rho(same_type: bool) -> float:
    key = "POOL_CORRELATION_SAME_TYPE" if same_type else "POOL_CORRELATION_CROSS_TYPE"
    default = DEFAULT_RHO_SAME_TYPE if same_type else DEFAULT_RHO_CROSS_TYPE
    try:
        value = float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default
    return min(max(value, 0.0), 1.0)


def compute_pooled_deviation(
    plants_actual: Dict[str, float],
    plants_schedule: Dict[str, float],
    pool_avc_mw: float,
    x: float,
) -> float:
    """Pooled deviation percentage for a realised block.

    Actuals are known here, so they simply net -- no correlation model is
    involved or needed. This is the settlement view; the forecasting view is
    `pool_quantiles` below.
    """
    total_actual = sum(plants_actual.values())
    total_schedule = sum(plants_schedule.values())

    denom = (x * pool_avc_mw) + ((1.0 - x) * total_schedule)
    if denom == 0.0:
        return 0.0

    return 100.0 * (total_actual - total_schedule) / denom


def pool_quantiles(plants_data: List[Dict]) -> Dict[float, float]:
    """Combine per-plant quantile fans into one pool-level fan.

    The median is summed; the spread around it is combined by variance addition
    with the assumed correlation. Returns {quantile_level: pooled_mw}.
    """
    if not plants_data:
        return {}

    levels = sorted(plants_data[0].get("quantile_forecasts", {}).keys())
    if not levels:
        return {}

    # Median is the reference point each plant's spread is measured from.
    medians = [
        float(p["quantile_forecasts"].get(0.5, p["quantile_forecasts"].get(0.50, 0.0)))
        for p in plants_data
    ]
    pooled_median = sum(medians)

    types = [str(p.get("asset_type", "solar")).lower() for p in plants_data]

    pooled: Dict[float, float] = {}
    for level in levels:
        # Each plant's signed distance from its own median at this quantile.
        deviations = [
            float(p["quantile_forecasts"].get(level, medians[i])) - medians[i]
            for i, p in enumerate(plants_data)
        ]

        # Variance addition across a correlated sum. The cross terms use the
        # pairwise correlation, which depends on whether the two plants share a
        # technology.
        combined = sum(d * d for d in deviations)
        for i in range(len(deviations)):
            for j in range(i + 1, len(deviations)):
                rho = _rho(types[i] == types[j])
                combined += 2.0 * rho * deviations[i] * deviations[j]

        magnitude = math.sqrt(combined) if combined > 0 else 0.0
        # All plants sit on the same side of their median at a given quantile,
        # so the sign of the naive sum is the sign of the pooled deviation.
        naive = sum(deviations)
        pooled[level] = pooled_median + math.copysign(magnitude, naive) if naive else pooled_median

    return pooled


def _dominant_asset_type(plants_data: List[Dict]) -> str:
    """The technology carrying the most capacity in the pool.

    The engine selects a tolerance band from asset type, and a mixed pool has no
    single correct band under the regulations as written. Weighting by capacity
    is the least-wrong choice available and is surfaced in the result so the
    assumption is visible rather than buried.
    """
    by_type: Dict[str, float] = {}
    for plant in plants_data:
        asset_type = str(plant.get("asset_type", "solar")).lower()
        by_type[asset_type] = by_type.get(asset_type, 0.0) + float(plant.get("avc_mw", 0.0) or 0.0)
    if not by_type:
        return "solar"
    return max(by_type.items(), key=lambda kv: kv[1])[0]


def compute_pooling_benefit(
    plants_data: List[Dict],
    dsm_engine,
    ncd: float,
    freq_hz: float,
) -> Dict:
    """Compare settling each plant alone against settling the pool, **for one block**.

    `plants_data` is the set of plants in the pool at a single instant -- one
    entry per plant, never per plant-block. For a whole day, use
    `compute_pooling_benefit_by_block`, which loops this over the 96 blocks.

    Deviation is a per-block quantity under CERC: a shortfall at 09:00 does not
    offset a surplus at 15:00, because they settle separately. Aggregating a
    day into a single call is therefore not a shortcut, it is a different and
    wrong calculation.
    """
    empty = {
        "individual_total_inr": 0.0,
        "pooled_total_inr": 0.0,
        "savings_inr": 0.0,
        "savings_pct": 0.0,
        "per_plant": [],
    }
    if not plants_data:
        return empty

    # A plant cannot appear twice in one pool at one instant. When it does, the
    # caller has flattened a time series into the plant axis -- which inflates
    # pool_avc_mw by the number of blocks, widens the tolerance band by the same
    # factor, and drives the pooled penalty to zero. Both API routes did exactly
    # this and reported a 100% pooling saving on the dashboard.
    seen = [p["plant_id"] for p in plants_data]
    duplicates = {pid for pid in seen if seen.count(pid) > 1}
    if duplicates:
        raise ValueError(
            f"compute_pooling_benefit received {len(seen)} entries covering only "
            f"{len(set(seen))} plants -- {sorted(duplicates)} appear more than once. "
            "This function settles ONE block; pass one entry per plant. For a full "
            "day use compute_pooling_benefit_by_block()."
        )

    individual_total_inr = 0.0
    per_plant = []

    for plant in plants_data:
        expected_penalty = dsm_engine.compute_expected_penalty(
            plant["quantile_forecasts"],
            plant["schedule_mw"],
            plant["avc_mw"],
            freq_hz,
            ncd,
            plant["asset_type"],
        )
        individual_total_inr += expected_penalty
        per_plant.append({"plant_id": plant["plant_id"], "individual_inr": expected_penalty})

    pool_avc_mw = sum(float(p.get("avc_mw", 0.0) or 0.0) for p in plants_data)
    pool_schedule_mw = sum(float(p.get("schedule_mw", 0.0) or 0.0) for p in plants_data)
    pooled_fan = pool_quantiles(plants_data)
    asset_type = _dominant_asset_type(plants_data)

    pooled_total_inr = dsm_engine.compute_expected_penalty(
        pooled_fan, pool_schedule_mw, pool_avc_mw, freq_hz, ncd, asset_type
    )

    # Reported without clamping. A single-plant "pool" saves nothing by
    # definition, and a genuinely unfavourable pool should be visible rather
    # than floored at zero -- a clamp here would have hidden the correlation bug
    # this module used to have.
    delta = individual_total_inr - pooled_total_inr
    savings_pct = (delta / individual_total_inr * 100.0) if individual_total_inr > 0 else 0.0

    same_type = len({str(p.get("asset_type", "solar")).lower() for p in plants_data}) == 1

    return {
        "individual_total_inr": individual_total_inr,
        "pooled_total_inr": pooled_total_inr,
        "savings_inr": delta,
        "savings_pct": savings_pct,
        "per_plant": per_plant,
        "pool_size": len(plants_data),
        "pool_avc_mw": pool_avc_mw,
        "asset_type_used": asset_type,
        "correlation_assumed": _rho(same_type),
        "beneficial": delta > 0,
    }


def allocate_pool_savings(
    individual_penalties: Dict[str, float],
    pooled_total: float,
) -> Dict[str, float]:
    """Split the pooled charge across members, pro-rata to what each would have
    paid alone.

    Pro-rata keeps the allocation simple and monotone: a plant that contributed
    more exposure pays more. It is not the only defensible rule -- Shapley value
    would attribute the diversification benefit more precisely -- but it is the
    one a counterparty can verify with a calculator.
    """
    sum_individual = sum(individual_penalties.values())
    if sum_individual == 0:
        return {plant_id: 0.0 for plant_id in individual_penalties}
    return {
        plant_id: pooled_total * (penalty / sum_individual)
        for plant_id, penalty in individual_penalties.items()
    }


def compute_pooling_benefit_by_block(
    blocks: List[List[Dict]],
    dsm_engine,
    ncd: float,
    freq_hz: float,
) -> Dict:
    """Pooling benefit across a whole day, settled block by block.

    `blocks` is one entry per time block, each holding the pool's plants at that
    instant -- i.e. `blocks[b]` is what `compute_pooling_benefit` expects.

    Summing per-block results is the only correct aggregation. Deviations settle
    per block under CERC, so a shortfall at 09:00 cannot offset a surplus at
    15:00, and collapsing the day into one call silently inflates the pool's
    Available Capacity (and therefore its tolerance band) by the number of
    blocks.
    """
    individual_total = 0.0
    pooled_total = 0.0
    per_plant: Dict[str, float] = {}
    meta: Dict = {}

    for block in blocks:
        if not block:
            continue
        result = compute_pooling_benefit(block, dsm_engine, ncd, freq_hz)
        individual_total += result["individual_total_inr"]
        pooled_total += result["pooled_total_inr"]
        for entry in result["per_plant"]:
            per_plant[entry["plant_id"]] = per_plant.get(entry["plant_id"], 0.0) + entry["individual_inr"]
        if not meta:
            meta = {
                "pool_size": result.get("pool_size", len(block)),
                "pool_avc_mw": result.get("pool_avc_mw", 0.0),
                "asset_type_used": result.get("asset_type_used", "solar"),
                "correlation_assumed": result.get("correlation_assumed"),
            }

    delta = individual_total - pooled_total
    savings_pct = (delta / individual_total * 100.0) if individual_total > 0 else 0.0

    return {
        "individual_total_inr": individual_total,
        "pooled_total_inr": pooled_total,
        "savings_inr": delta,
        "savings_pct": savings_pct,
        "per_plant": [
            {"plant_id": pid, "individual_inr": value} for pid, value in per_plant.items()
        ],
        "blocks_settled": len([b for b in blocks if b]),
        "beneficial": delta > 0,
        **meta,
    }
