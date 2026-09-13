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
1. **Probability-weighted expectation.** Each quantile is weighted by the
   probability mass it actually represents (midpoint rule). The weights come
   from `backend.modules.dsm.engine.quantile_weights`, which
   `DSMEngine.compute_expected_penalty` also uses, so the optimiser, the DSM
   route, the dashboard and pooling all report the same expected penalty.

2. **A real search.** The previous version tried five candidates, all of them
   forecast quantiles. The penalty curve is piecewise-linear in the declared
   schedule with kinks at the tolerance-band edges, and its minimum frequently
   sits *between* two quantiles -- so restricting candidates to quantile values
   systematically misses it. This searches a fine grid over [0, AvC] with the
   quantiles included as exact candidates.

Battery storage
---------------
With `battery_capacity_mwh` > 0 the schedule is chosen together with a battery
that responds to each forecast outcome -- see battery_recourse.py for the model
and for why a battery plan fixed a day ahead cannot lower a DSM penalty. With no
battery, dispatch is reported as zeros and `battery_modelled` is False, so the
two cannot be mistaken for each other.
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

    Defined once, in the DSM engine, so the optimiser and every other penalty
    calculation weight quantiles identically.
    """
    from backend.modules.dsm.engine import quantile_weights as _engine_weights

    return _engine_weights(levels)


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
                    "schedule_saving_inr": round(naive_penalty - best_penalty, 2),
                    "battery_saving_inr": 0.0,
                }
            )

        optimised_without_battery = optimised_total

        battery_modelled = False
        if float(battery_capacity_mwh or 0.0) > 0 and forecast_blocks:
            try:
                from backend.modules.optimize.battery_recourse import optimise_with_battery

                with_battery = optimise_with_battery(
                    forecast_blocks=forecast_blocks,
                    avc_mw=avc_mw,
                    dsm_engine=dsm_engine,
                    capacity_mwh=float(battery_capacity_mwh),
                    ncd=ncd,
                    freq_hz=freq_hz,
                    asset_type=asset_type,
                )
                optimised_schedule = with_battery["schedule"]
                battery_dispatch = with_battery["dispatch"]
                per_block = with_battery["per_block"]
                optimised_total = with_battery["total_inr"]
                battery_modelled = True
            except Exception as exc:  # noqa: BLE001
                # The no-battery result is already complete and correct, so a
                # failure degrades to it, visibly, rather than to a guess.
                logger.warning("battery model failed (%s); reporting the no-battery optimum", exc)

        savings_inr = naive_total - optimised_total
        savings_pct = (savings_inr / naive_total * 100.0) if naive_total > 0 else 0.0

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
                + ("+battery_recourse" if battery_modelled else "")
            ),
            # True only when a battery was requested and modelled. False means the
            # dispatch is zeros because there is no battery, not because one idled.
            "battery_modelled": battery_modelled,
            # The optimum with no battery, so the battery's own contribution can be
            # shown rather than folded silently into one total.
            "optimised_without_battery_inr": optimised_without_battery,
            "battery_saving_inr": max(optimised_without_battery - optimised_total, 0.0),
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
            # A storage card claims only the battery's share of a block's saving,
            # and a scheduling card only the schedule's, so the rupees on the cards
            # never add up to more than the optimiser actually saved.
            battery_saving = row.get("battery_saving_inr", 0.0)
            battery_mw = max(row.get("charge_mw", 0.0), row.get("discharge_mw", 0.0))
            if battery_saving > 0 and battery_mw >= material:
                charging = row.get("charge_mw", 0.0) >= row.get("discharge_mw", 0.0)
                cards.append(
                    {
                        "type": "storage_dispatch",
                        "block_no": row["block_no"],
                        "mw": battery_mw,
                        "reason": (
                            f"{'Charge' if charging else 'Discharge'} the battery by up to "
                            f"{battery_mw:.2f} MW if output lands "
                            f"{'above' if charging else 'below'} schedule, holding the "
                            f"deviation at the edge of the tolerance band."
                        ),
                        "inr_impact": battery_saving,
                    }
                )

            if row.get("schedule_saving_inr", row["saving_inr"]) <= 0:
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
                        "inr_impact": row.get("schedule_saving_inr", row["saving_inr"]),
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
                        "inr_impact": row.get("schedule_saving_inr", row["saving_inr"]),
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
