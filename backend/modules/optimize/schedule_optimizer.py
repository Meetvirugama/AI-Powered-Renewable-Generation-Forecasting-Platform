"""Min-rupee day-ahead schedule optimiser.

Picks the schedule to declare for each of the 96 blocks so that the *expected*
DSM penalty is as low as possible, given the probabilistic forecast for that
block and the CERC rules in backend/modules/dsm/engine.py.

The problem separates by block
------------------------------
Without a battery, nothing couples one block to the next: the penalty for block
k depends only on the schedule declared for block k and the generation that
actually occurs in it. So optimising each block independently is not a heuristic
-- it is globally optimal for this objective. That is why this is a per-block
1-D search rather than a 96-dimensional one.

Two things this does better than the coarse optimiser it replaces
-----------------------------------------------------------------
1. **Probability-weighted expectation.** `DSMEngine.compute_expected_penalty`
   averages the per-quantile penalties with equal weight, but P05 and P50 are
   not equally likely outcomes -- equal weighting triples the influence of the
   tails. This module weights each quantile by the probability mass it actually
   represents (midpoint rule) and sums, using the engine's own
   `compute_block_penalty` as the per-scenario primitive. The engine is left
   untouched; only the aggregation here is corrected.

2. **A real search.** The previous version tried five candidates, all of them
   forecast quantiles. The penalty curve is piecewise-linear in the declared
   schedule with kinks at the tolerance-band edges, and its minimum frequently
   sits *between* two quantiles -- so restricting candidates to quantile values
   systematically misses it. This searches a fine grid over [0, AvC] with the
   quantiles included as exact candidates.

Battery dispatch is reported as zeros, honestly: the 96-block battery LP
(`battery_lp.py`, PuLP/CBC) is not implemented. Reporting a fabricated dispatch
would be worse than reporting none.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("renewable_platform")

# Candidate schedule levels per block, spread over [0, AvC]. 201 points on a
# 50 MW plant is a 0.25 MW resolution -- finer than any RLDC accepts a
# declaration at, so the grid is not the limiting factor.
GRID_POINTS = int(os.getenv("OPTIMIZER_GRID_POINTS", "201"))

# Quantile levels the forecast engines emit, in order.
QUANTILE_LEVELS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


def quantile_weights(levels: tuple[float, ...] = QUANTILE_LEVELS) -> dict[float, float]:
    """Probability mass to attribute to each quantile sample.

    Midpoint rule: the sample at level q_i stands for the interval halfway to
    its neighbours, with 0 and 1 as the outer edges. Weights are normalised so
    they sum to exactly 1, which makes the result a true expected rupee value
    rather than an average of penalties.
    """
    ordered = sorted(levels)
    weights: dict[float, float] = {}
    for i, q in enumerate(ordered):
        lower = ordered[i - 1] if i > 0 else 0.0
        upper = ordered[i + 1] if i + 1 < len(ordered) else 1.0
        weights[q] = (upper - lower) / 2.0
    total = sum(weights.values()) or 1.0
    return {q: w / total for q, w in weights.items()}


_WEIGHTS = quantile_weights()


def _block_quantiles(block: dict) -> dict[float, float]:
    """Pull the quantile fan out of a forecast block, tolerating partial sets."""
    mapping = {
        0.05: "p05", 0.10: "p10", 0.25: "p25",
        0.50: "p50", 0.75: "p75", 0.90: "p90", 0.95: "p95",
    }
    out = {}
    for level, key in mapping.items():
        value = block.get(key)
        if value is not None:
            out[level] = float(value)
    if not out:
        raise ValueError(f"forecast block {block.get('block_no')} carries no quantiles")
    return out


def expected_penalty(
    dsm_engine: Any,
    quantiles: dict[float, float],
    schedule_mw: float,
    avc_mw: float,
    freq_hz: float,
    ncd: float,
    asset_type: str,
) -> float:
    """Probability-weighted expected penalty for declaring `schedule_mw`."""
    total = 0.0
    weight_sum = 0.0
    for level, actual_mw in quantiles.items():
        weight = _WEIGHTS.get(level, 1.0 / len(quantiles))
        penalty = dsm_engine.compute_block_penalty(
            actual_mw, schedule_mw, avc_mw, freq_hz, ncd, asset_type
        )
        total += weight * penalty
        weight_sum += weight
    return total / weight_sum if weight_sum else 0.0


def _candidates(quantiles: dict[float, float], avc_mw: float) -> list[float]:
    """Search grid: a uniform sweep over [0, AvC] plus the exact quantile values.

    The quantiles are included explicitly because the penalty curve's kinks sit
    at band edges relative to them, and a uniform grid can straddle a narrow
    optimum without ever landing on it.

    The upper bound is Available Capacity, never the forecast. A generator
    cannot declare more than it has available, so a schedule above AvC is not
    something an RLDC would accept -- even in a block where the forecast happens
    to exceed it. With no capacity there is nothing to declare.
    """
    if avc_mw <= 0:
        return [0.0]
    step = avc_mw / (GRID_POINTS - 1)
    grid = [i * step for i in range(GRID_POINTS)]
    grid.extend(v for v in quantiles.values() if 0.0 <= v <= avc_mw)
    return sorted(set(round(v, 6) for v in grid))


class ProductionScheduleOptimizer:
    """Grid-search optimiser over the real CERC DSM engine.

    Constructed by backend.modules.factory when OPTIMIZER_TYPE=production.
    Stateless and cheap to build -- all the work happens per call.
    """

    def optimize_day_ahead(
        self,
        forecast_blocks: list[dict],
        avc_mw: float,
        dsm_engine: Any,
        ncd: float = 450.0,
        freq_hz: float = 50.0,
        asset_type: str = "solar",
        battery_capacity_mwh: float = 0.0,
        **kwargs: Any,
    ) -> dict:
        avc_mw = float(avc_mw or 0.0)

        optimised_schedule: list[float] = []
        naive_schedule: list[float] = []
        battery_dispatch: list[dict] = []
        per_block: list[dict] = []

        naive_total = 0.0
        optimised_total = 0.0

        for block in forecast_blocks:
            block_no = int(block.get("block_no", len(optimised_schedule) + 1))
            quantiles = _block_quantiles(block)
            p50_raw = quantiles.get(0.50, sorted(quantiles.values())[len(quantiles) // 2])
            # The naive baseline has to be declarable too, or the comparison is
            # against a schedule no RLDC would accept.
            p50 = min(max(p50_raw, 0.0), avc_mw) if avc_mw > 0 else 0.0

            # The naive strategy every generator starts from: declare the median.
            naive_penalty = expected_penalty(
                dsm_engine, quantiles, p50, avc_mw, freq_hz, ncd, asset_type
            )

            best_schedule = p50
            best_penalty = naive_penalty
            for candidate in _candidates(quantiles, avc_mw):
                penalty = expected_penalty(
                    dsm_engine, quantiles, candidate, avc_mw, freq_hz, ncd, asset_type
                )
                if penalty < best_penalty - 1e-9:
                    best_penalty = penalty
                    best_schedule = candidate

            naive_schedule.append(round(p50, 4))
            optimised_schedule.append(round(best_schedule, 4))
            naive_total += naive_penalty
            optimised_total += best_penalty

            battery_dispatch.append(
                {"block_no": block_no, "charge_mw": 0.0, "discharge_mw": 0.0, "soc_mwh": 0.0}
            )
            per_block.append(
                {
                    "block_no": block_no,
                    "p50_mw": round(p50, 4),
                    "optimised_mw": round(best_schedule, 4),
                    "shift_mw": round(best_schedule - p50, 4),
                    "naive_penalty_inr": round(naive_penalty, 2),
                    "optimised_penalty_inr": round(best_penalty, 2),
                    "saving_inr": round(naive_penalty - best_penalty, 2),
                }
            )

        savings_inr = naive_total - optimised_total
        savings_pct = (savings_inr / naive_total * 100.0) if naive_total > 0 else 0.0

        # Battery LP: run after the per-block grid-search so the no-battery
        # optimum serves as the linearisation point for the LP objective.
        battery_modelled = False
        if float(battery_capacity_mwh or 0.0) > 0:
            try:
                from backend.modules.optimize.battery_lp import solve_battery_dispatch
                battery_dispatch = solve_battery_dispatch(
                    forecast_blocks=forecast_blocks,
                    optimised_schedules=optimised_schedule,
                    dsm_engine=dsm_engine,
                    avc_mw=avc_mw,
                    battery_capacity_mwh=float(battery_capacity_mwh),
                    ncd=ncd,
                    freq_hz=freq_hz,
                    asset_type=asset_type,
                )
                battery_modelled = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("battery LP failed (%s); dispatch set to zeros", exc)

        logger.info(
            "optimiser: naive=%.2f optimised=%.2f saving=%.2f (%.1f%%) over %d blocks",
            naive_total, optimised_total, savings_inr, savings_pct, len(per_block),
        )

        return {
            "optimised_schedule": optimised_schedule,
            "naive_schedule": naive_schedule,
            "battery_dispatch": battery_dispatch,
            "naive_total_inr": naive_total,
            "optimised_total_inr": optimised_total,
            "savings_inr": savings_inr,
            "savings_pct": savings_pct,
            "action_cards": self._action_cards(per_block, avc_mw),
            "per_block": per_block,
            "method": (
                f"grid_search_{GRID_POINTS}pt_probability_weighted"
                + ("+battery_lp_highs" if battery_modelled else "")
            ),
            # True when battery_capacity_mwh > 0 and the LP solved successfully.
            # False (zero dispatch) otherwise — never mislead about what ran.
            "battery_modelled": battery_modelled,
        }

    @staticmethod
    def _action_cards(per_block: list[dict], avc_mw: float) -> list[dict]:
        """Operator-facing actions, derived from what the optimiser actually did.

        Every card is tied to a real rupee delta the optimiser computed, rather
        than to a threshold on the forecast. A card that cannot name what it
        saves is not worth showing an operator.
        """
        cards: list[dict] = []
        if not per_block:
            return cards

        material = max(0.01 * avc_mw, 0.05)

        for row in per_block:
            if row["saving_inr"] <= 0:
                continue
            shift = row["shift_mw"]
            if abs(shift) < material:
                continue

            if shift < 0:
                cards.append(
                    {
                        "type": "curtailment",
                        "block_no": row["block_no"],
                        "mw": abs(shift),
                        "reason": (
                            f"Declare {abs(shift):.2f} MW below the P50 forecast. The upside "
                            f"of the forecast band risks over-injection beyond the tolerance "
                            f"band; under-declaring keeps the deviation inside it."
                        ),
                        "inr_impact": row["saving_inr"],
                    }
                )
            else:
                cards.append(
                    {
                        "type": "reserve_flag",
                        "block_no": row["block_no"],
                        "mw": shift,
                        "reason": (
                            f"Declare {shift:.2f} MW above the P50 forecast. The downside of "
                            f"the band is the costlier tail here, so a higher declaration "
                            f"lowers expected charges."
                        ),
                        "inr_impact": row["saving_inr"],
                    }
                )

        # Blocks that stay expensive even after optimising are where an operator
        # should look for a physical remedy rather than a scheduling one.
        residual = sorted(per_block, key=lambda r: -r["optimised_penalty_inr"])[:3]
        for row in residual:
            if row["optimised_penalty_inr"] <= 0:
                continue
            cards.append(
                {
                    "type": "high_risk_block",
                    "block_no": row["block_no"],
                    "mw": row["optimised_mw"],
                    "reason": (
                        "Highest residual exposure after optimisation. Forecast uncertainty "
                        "here is too wide for scheduling alone to neutralise; battery or "
                        "curtailment would be needed."
                    ),
                    "inr_impact": row["optimised_penalty_inr"],
                }
            )

        cards.sort(key=lambda c: -c["inr_impact"])
        return cards[:12]
