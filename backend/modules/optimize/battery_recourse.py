"""Battery storage as real-time recourse against DSM deviation charges.

Why the previous battery LP could not save anything
---------------------------------------------------
The earlier module planned a fixed charge/discharge profile for the day and
optimised it against a linearised penalty. It dispatched hundreds of MWh and
never changed `optimised_total_inr` by a rupee, at any battery size.

That was not a wiring bug. A DSM penalty depends on how far delivered output
lands from the declared schedule. Shifting delivered output by a fixed amount
in a block is, to that penalty, the same as declaring a different schedule --
and the schedule optimiser already searches every declarable schedule from 0
to Available Capacity. A plan fixed a day ahead therefore adds nothing the
schedule search had not already found. (Exact while the CERC X-parameter is 1,
as in 2026; approximate as X falls, because the deviation denominator starts to
include the schedule.)

What a battery actually does against deviation
----------------------------------------------
It reacts. Once a block's real output is known, the battery absorbs an
over-injection or covers an under-injection, pulling the deviation back to the
edge of the tolerance band. Its value comes from *uncertainty*, which a fixed
plan cannot address and recourse can.

Scenario paths, and why not one expected state of charge
--------------------------------------------------------
Each forecast quantile is treated as a whole-day path: on the P05 path every
block comes in at its own P05, on the P95 path at its P95. Each path keeps its
own state of charge through the day.

An earlier draft of this module tracked a single *expected* state of charge,
and it claimed a half-hour battery eliminated 100% of a day's DSM penalty on a
1,000 MW plant. That was an artefact. Within every block the battery absorbed
the high outcomes and covered the low ones; in expectation those cancel, so the
modelled battery never emptied or filled. A real cloudy day stays below
forecast all day, and a real battery covering it runs out within hours.

Per-path state of charge restores that. On the low path the battery drains and
stops helping; on the high path it fills and stops absorbing. Treating errors as
fully persistent across the day is deliberately conservative: if forecast errors
were independent from block to block, a battery would do somewhat better than
this model reports.

The model, per block
--------------------
For each path, given that path's current state of charge:

    deviation = actual - schedule
    outside the band and priced   ->  charge or discharge just enough to bring
                                      |deviation| back to the band edge,
                                      limited by power and that path's charge
    inside the band, or unpriced  ->  do nothing (energy is not spent for free)

The expected penalty is probability-weighted over the paths, exactly as the
schedule optimiser weights quantiles. The declared schedule and the battery
response are chosen together per block, and every path's state of charge then
advances by its own charge or discharge.

Guarantee
---------
A correction only moves a deviation toward the band and never across zero, so
it cannot flip over-injection into under-injection or raise a penalty. For any
schedule the battery-assisted penalty is therefore at most the unassisted one,
and the battery-assisted optimum is never worse than the no-battery optimum.
tests/test_schedule_optimizer.py asserts this.

Remaining limit
---------------
The search is greedy through the day: it does not hold energy back in the
morning for an expensive evening block. Doing that optimally is a stochastic
dynamic programme and is out of scope here.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("renewable_platform")

DT_HOURS = 0.25

# A standard grid battery delivers its full energy over two hours.
DEFAULT_DURATION_HOURS = 2.0

# One-way efficiency; the round trip is its square (~90%).
DEFAULT_EFFICIENCY = 0.95

DEFAULT_INITIAL_SOC_FRACTION = 0.5

# Stop a hair inside the band edge. The engine treats |deviation| == band as
# within tolerance, and floating-point noise must not push a corrected value
# back out of it.
_EDGE = 1.0 - 1e-9


def allowed_deviation_mw(dsm_engine: Any, schedule_mw: float, avc_mw: float, asset_type: str) -> float:
    """Largest |actual - schedule| that stays inside the tolerance band, in MW.

    Mirrors DSMEngine.compute_deviation_pct, whose denominator is
    X * AvC + (1 - X) * schedule, so the band narrows with the schedule as the
    CERC X-trajectory falls from 2026 towards 2031.
    """
    band = dsm_engine.solar_band if asset_type.lower() == "solar" else dsm_engine.wind_band
    x = float(getattr(dsm_engine, "x", 1.0))
    denominator = x * avc_mw + (1.0 - x) * schedule_mw
    return max(band * denominator, 0.0)


def _room(room: float | dict[float, float], level: float) -> float:
    return max(room.get(level, 0.0) if isinstance(room, dict) else room, 0.0)


def block_with_battery(
    dsm_engine: Any,
    quantiles: dict[float, float],
    weights: dict[float, float],
    schedule_mw: float,
    avc_mw: float,
    freq_hz: float,
    ncd: float,
    asset_type: str,
    charge_room_mw: float | dict[float, float],
    discharge_room_mw: float | dict[float, float],
) -> dict:
    """Expected penalty for one block when a battery responds to each outcome.

    `charge_room_mw` and `discharge_room_mw` are either one headroom for every
    path or a headroom per quantile level, since each path carries its own state
    of charge. Returns the expected penalty with and without the battery, the
    expected charge and discharge, and each path's own charge and discharge.
    """
    limit = allowed_deviation_mw(dsm_engine, schedule_mw, avc_mw, asset_type) * _EDGE

    expected = {"with": 0.0, "without": 0.0, "charge": 0.0, "discharge": 0.0}
    per_level: dict[float, tuple[float, float]] = {}
    weight_sum = 0.0

    for level, actual in quantiles.items():
        weight = weights.get(level, 1.0 / len(quantiles))
        unassisted = dsm_engine.compute_block_penalty(
            actual, schedule_mw, avc_mw, freq_hz, ncd, asset_type
        )

        charge = discharge = 0.0
        # Only spend energy on a deviation that actually costs money. Over-injection
        # at high grid frequency, for one, is unpriced -- absorbing it would drain
        # the battery for nothing.
        if unassisted > 0.0:
            deviation = actual - schedule_mw
            if deviation > limit:
                charge = min(deviation - limit, _room(charge_room_mw, level))
            elif deviation < -limit:
                discharge = min(-deviation - limit, _room(discharge_room_mw, level))

        if charge or discharge:
            assisted = dsm_engine.compute_block_penalty(
                actual - charge + discharge, schedule_mw, avc_mw, freq_hz, ncd, asset_type
            )
            # Defensive: a correction toward the band can only lower the charge.
            assisted = min(assisted, unassisted)
        else:
            assisted = unassisted

        per_level[level] = (charge, discharge)
        expected["with"] += weight * assisted
        expected["without"] += weight * unassisted
        expected["charge"] += weight * charge
        expected["discharge"] += weight * discharge
        weight_sum += weight

    if weight_sum:
        for key in expected:
            expected[key] /= weight_sum
    return {**expected, "per_level": per_level}


def optimise_with_battery(
    forecast_blocks: list[dict],
    avc_mw: float,
    dsm_engine: Any,
    capacity_mwh: float,
    ncd: float = 450.0,
    freq_hz: float = 50.0,
    asset_type: str = "solar",
    power_mw: float | None = None,
    efficiency: float = DEFAULT_EFFICIENCY,
    initial_soc_fraction: float = DEFAULT_INITIAL_SOC_FRACTION,
) -> dict:
    """Choose each block's schedule together with the battery's response to it."""
    # Imported here: schedule_optimizer imports this module.
    from backend.modules.optimize.schedule_optimizer import (
        _WEIGHTS,
        _block_quantiles,
        _candidates,
        expected_penalty,
    )

    capacity = max(float(capacity_mwh), 0.0)
    power = float(power_mw) if power_mw else capacity / DEFAULT_DURATION_HOURS
    initial_soc = initial_soc_fraction * capacity
    # One state of charge per scenario path, created as each level first appears.
    path_soc: dict[float, float] = {}

    schedule: list[float] = []
    dispatch: list[dict] = []
    per_block: list[dict] = []
    total = 0.0

    for block in forecast_blocks:
        block_no = int(block.get("block_no", len(schedule) + 1))
        quantiles = _block_quantiles(block)
        for level in quantiles:
            path_soc.setdefault(level, initial_soc)

        p50_raw = quantiles.get(0.50, sorted(quantiles.values())[len(quantiles) // 2])
        p50 = min(max(p50_raw, 0.0), avc_mw) if avc_mw > 0 else 0.0
        naive_penalty = expected_penalty(dsm_engine, quantiles, p50, avc_mw, freq_hz, ncd, asset_type)

        # Headroom for this block on each path, from the energy that path's
        # battery can still take in or give out.
        charge_room = {
            lvl: min(power, max(capacity - path_soc[lvl], 0.0) / (DT_HOURS * efficiency))
            for lvl in quantiles
        }
        discharge_room = {
            lvl: min(power, max(path_soc[lvl], 0.0) * efficiency / DT_HOURS)
            for lvl in quantiles
        }

        def evaluate(candidate: float) -> dict:
            return block_with_battery(
                dsm_engine, quantiles, _WEIGHTS, candidate, avc_mw, freq_hz, ncd,
                asset_type, charge_room, discharge_room,
            )

        # P50 is the starting point, as in the no-battery search, so the per-block
        # guarantee against that search holds even when P50 is off the grid.
        best_mw, best = p50, evaluate(p50)
        for candidate in _candidates(quantiles, avc_mw):
            outcome = evaluate(candidate)
            cheaper = outcome["with"] < best["with"] - 1e-9
            # On a tie, prefer the schedule that works the battery less.
            tie_but_lighter = (
                abs(outcome["with"] - best["with"]) <= 1e-9
                and outcome["charge"] + outcome["discharge"]
                < best["charge"] + best["discharge"] - 1e-9
            )
            if cheaper or tie_but_lighter:
                best_mw, best = candidate, outcome

        for lvl, (charge, discharge) in best["per_level"].items():
            updated = path_soc[lvl] + DT_HOURS * (efficiency * charge - discharge / efficiency)
            path_soc[lvl] = min(max(updated, 0.0), capacity)

        weight_total = sum(_WEIGHTS.get(lvl, 0.0) for lvl in quantiles) or 1.0
        expected_soc = sum(_WEIGHTS.get(lvl, 0.0) * path_soc[lvl] for lvl in quantiles) / weight_total

        schedule.append(round(best_mw, 4))
        dispatch.append({
            "block_no": block_no,
            "charge_mw": round(best["charge"], 4),
            "discharge_mw": round(best["discharge"], 4),
            # Probability-weighted across the scenario paths.
            "soc_mwh": round(expected_soc, 4),
        })
        per_block.append({
            "block_no": block_no,
            "p50_mw": round(p50, 4),
            "optimised_mw": round(best_mw, 4),
            "shift_mw": round(best_mw - p50, 4),
            "naive_penalty_inr": round(naive_penalty, 2),
            "optimised_penalty_inr": round(best["with"], 2),
            "saving_inr": round(naive_penalty - best["with"], 2),
            # The saving split in two, so an action card never claims the other's share.
            "schedule_saving_inr": round(naive_penalty - best["without"], 2),
            "battery_saving_inr": round(best["without"] - best["with"], 2),
            "charge_mw": round(best["charge"], 4),
            "discharge_mw": round(best["discharge"], 4),
        })
        total += best["with"]

    logger.info(
        "battery recourse: capacity=%.1f MWh power=%.1f MW expected charge=%.2f MWh discharge=%.2f MWh",
        capacity, power,
        sum(d["charge_mw"] for d in dispatch) * DT_HOURS,
        sum(d["discharge_mw"] for d in dispatch) * DT_HOURS,
    )
    return {"schedule": schedule, "dispatch": dispatch, "per_block": per_block, "total_inr": total}
