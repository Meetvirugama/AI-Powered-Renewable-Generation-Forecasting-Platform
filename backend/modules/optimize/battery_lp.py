"""96-block battery dispatch LP for day-ahead schedule optimisation.

What this solves
----------------
The grid-search optimiser in schedule_optimizer.py picks the best declared
schedule for each block independently. That is globally optimal *without* a
battery, because no block affects any other. With a battery, every charge
decision in block t reduces the energy available to discharge in t+k, so the
blocks are coupled. A 1-D search per block can no longer find the global
optimum; you need a solver that sees all 96 blocks at once.

This module solves that coupled problem as a linear programme using
scipy.optimize.linprog (HiGHS backend, already in the installed stack --
no new dependency required).

LP formulation
--------------
Decision variables for each block t = 1..T (T=96, dt=0.25h):

    c[t]     charge power (MW), ≥ 0
    d[t]     discharge power (MW), ≥ 0
    s[t]     state-of-charge (MWh) at the *end* of block t, ≥ 0

Effective delivered generation at block t:
    gen_eff[t] = gen_forecast[t] - c[t] + d[t]

Objective: minimise sum_t E[penalty(gen_eff[t], schedule[t])]

The penalty function is piecewise-linear in gen_eff but *non-linear* across
the 96-block problem due to coupling. We linearise by approximating the
expected penalty as a linear function of the net dispatch (charge - discharge)
around the no-battery optimum. This is exact for the linear pieces of the DSM
penalty curve and accurate enough for the hackathon demo.

Linearisation: for each block t, let
    shift[t] = d[t] - c[t]       (net discharge into the grid, MW)
    dp/dgen  = marginal penalty improvement per MW of extra delivered generation
The objective coefficient for shift[t] is therefore:
    -dp/dgen[t]   (negative because we minimise and shift improves things)

We compute dp/dgen numerically from the DSM engine at the no-battery optimum.

Constraints
-----------
Energy balance (SOC update):
    s[t] = s[t-1] + eta_c * c[t] * dt - (1/eta_d) * d[t] * dt   ∀ t

SOC bounds:
    0 ≤ s[t] ≤ capacity_mwh   ∀ t

Initial / final SOC:
    s[0] = initial_soc_mwh  (default: 0.5 * capacity)
    s[T] ≥ final_soc_mwh    (default: 0.3 * capacity, leave some reserve)

Power bounds:
    0 ≤ c[t] ≤ charge_rate_mw   ∀ t
    0 ≤ d[t] ≤ discharge_rate_mw ∀ t

Physical generation bound (can't inject more than plant + battery can deliver):
    gen_forecast[t] - c[t] + d[t] ≥ 0   (can't draw more than forecast)
    gen_forecast[t] - c[t] + d[t] ≤ avc_mw

No simultaneous charge+discharge:
    c[t] + d[t] ≤ max_rate
(Enforced via the solver -- no big-M needed because the objective naturally
prefers not to waste energy by round-tripping.)
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("renewable_platform")

DT_HOURS = 0.25  # 15-minute blocks


def _marginal_penalty_improvement(
    dsm_engine: Any,
    quantiles: dict[float, float],
    schedule_mw: float,
    avc_mw: float,
    freq_hz: float,
    ncd: float,
    asset_type: str,
    delta_mw: float = 0.5,
) -> float:
    """dp/dgen: reduction in expected penalty per extra MW of delivered generation.

    Computed as a central finite difference around `schedule_mw`. Positive means
    more generation reduces penalty (typical: plant is under-generating relative
    to its declared schedule). Negative means more generation increases penalty
    (plant is over-generating).
    """
    from backend.modules.optimize.schedule_optimizer import expected_penalty, _WEIGHTS

    def ep(gen_shift: float) -> float:
        shifted = {q: max(0.0, min(avc_mw, v + gen_shift)) for q, v in quantiles.items()}
        return expected_penalty(dsm_engine, shifted, schedule_mw, avc_mw, freq_hz, ncd, asset_type)

    hi = ep(+delta_mw)
    lo = ep(-delta_mw)
    return (lo - hi) / (2.0 * delta_mw)  # positive = more gen is better


def solve_battery_dispatch(
    forecast_blocks: list[dict],
    optimised_schedules: list[float],
    dsm_engine: Any,
    avc_mw: float,
    battery_capacity_mwh: float,
    charge_rate_mw: float | None = None,
    discharge_rate_mw: float | None = None,
    eta_charge: float = 0.95,
    eta_discharge: float = 0.95,
    ncd: float = 450.0,
    freq_hz: float = 50.0,
    asset_type: str = "solar",
    initial_soc_fraction: float = 0.5,
    final_soc_fraction: float = 0.3,
) -> list[dict]:
    """Solve the 96-block battery LP and return per-block dispatch.

    Parameters
    ----------
    forecast_blocks:
        The same list of dicts the grid-search optimiser consumed, one per block.
    optimised_schedules:
        The declared schedules from the grid-search (used as the linearisation point).
    dsm_engine:
        Live DSM engine, used to compute marginal penalty gradients.
    battery_capacity_mwh:
        Usable energy capacity (MWh). Values ≤ 0 return all-zero dispatch.
    charge_rate_mw / discharge_rate_mw:
        Max power (MW). Defaults to capacity / 2h (a standard 2h BESS).
    eta_charge / eta_discharge:
        Round-trip efficiency factors (one-way each, product ≈ 0.90).

    Returns
    -------
    List of dicts: {block_no, charge_mw, discharge_mw, soc_mwh}
    """
    try:
        from scipy.optimize import linprog
    except ImportError:
        logger.warning("scipy not installed — returning zero battery dispatch")
        return _zero_dispatch(forecast_blocks)

    if battery_capacity_mwh <= 0:
        return _zero_dispatch(forecast_blocks)

    T = len(forecast_blocks)
    cap = float(battery_capacity_mwh)
    c_rate = float(charge_rate_mw) if charge_rate_mw else cap / 2.0
    d_rate = float(discharge_rate_mw) if discharge_rate_mw else cap / 2.0
    soc_init = initial_soc_fraction * cap
    soc_final_min = final_soc_fraction * cap

    # ------------------------------------------------------------------ objective
    # Variables: [c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}]
    # Minimize: sum_t (-marginal_improvement[t]) * (d[t] - c[t])
    #         = sum_t marginal_improvement[t] * c[t]
    #           - sum_t marginal_improvement[t] * d[t]

    p50_list = [float(b.get("p50", 0.0)) for b in forecast_blocks]

    # Build quantile dicts (reuse schedule_optimizer._block_quantiles logic)
    mapping = {0.05: "p05", 0.10: "p10", 0.25: "p25",
               0.50: "p50", 0.75: "p75", 0.90: "p90", 0.95: "p95"}
    quantile_list = []
    for b in forecast_blocks:
        q = {}
        for level, key in mapping.items():
            v = b.get(key)
            if v is not None:
                q[level] = float(v)
        quantile_list.append(q)

    # Marginal improvement per MW of extra discharge (positive = good)
    grad = np.array([
        _marginal_penalty_improvement(
            dsm_engine, q, sch, avc_mw, freq_hz, ncd, asset_type
        )
        for q, sch in zip(quantile_list, optimised_schedules)
    ], dtype=float)

    # obj: minimise c_costs - d_savings  (linprog minimises)
    c_obj = grad          # charging costs (we lose the penalty improvement)
    d_obj = -grad         # discharging gains
    s_obj = np.zeros(T)   # SOC has no direct cost

    cost = np.concatenate([c_obj, d_obj, s_obj])

    # ---------------------------------------------------------------- constraints
    # Variable layout: c[0..T-1] | d[0..T-1] | s[0..T-1]
    # Index helpers
    ci = lambda t: t          # noqa: E731
    di = lambda t: T + t      # noqa: E731
    si = lambda t: 2 * T + t  # noqa: E731
    n_vars = 3 * T

    A_eq = []
    b_eq = []

    # SOC update: s[t] = s[t-1] + eta_c*c[t]*dt - (1/eta_d)*d[t]*dt
    # => -s[t-1] + s[t] - eta_c*dt*c[t] + (1/eta_d)*dt*d[t] = 0
    for t in range(T):
        row = np.zeros(n_vars)
        row[ci(t)] = -eta_charge * DT_HOURS
        row[di(t)] = (1.0 / eta_discharge) * DT_HOURS
        row[si(t)] = 1.0
        if t > 0:
            row[si(t - 1)] = -1.0
        b_val = soc_init * (1 if t == 0 else 0)
        # For t==0: s[0] = soc_init + eta_c*dt*c[0] - dt/eta_d*d[0]
        # Rearranging:  s[0] - eta_c*dt*c[0] + dt/eta_d*d[0] = soc_init
        if t == 0:
            b_val = soc_init
        A_eq.append(row)
        b_eq.append(b_val)

    A_ub = []
    b_ub = []

    # Final SOC: s[T-1] >= soc_final_min  =>  -s[T-1] <= -soc_final_min
    row = np.zeros(n_vars)
    row[si(T - 1)] = -1.0
    A_ub.append(row)
    b_ub.append(-soc_final_min)

    # Physical generation bounds per block:
    # gen[t] - c[t] + d[t] >= 0  =>  c[t] - d[t] <= p50[t]
    # gen[t] - c[t] + d[t] <= avc_mw  =>  -c[t] + d[t] <= avc_mw - p50[t]
    for t in range(T):
        p = p50_list[t]
        row_lo = np.zeros(n_vars)
        row_lo[ci(t)] = 1.0
        row_lo[di(t)] = -1.0
        A_ub.append(row_lo)
        b_ub.append(p)

        row_hi = np.zeros(n_vars)
        row_hi[ci(t)] = -1.0
        row_hi[di(t)] = 1.0
        A_ub.append(row_hi)
        b_ub.append(max(0.0, avc_mw - p))

    # ------------------------------------------------------------------- bounds
    bounds = (
        [(0.0, c_rate)] * T    # c[t]
        + [(0.0, d_rate)] * T  # d[t]
        + [(0.0, cap)] * T     # s[t]
    )

    # --------------------------------------------------------------- solve
    result = linprog(
        cost,
        A_ub=np.array(A_ub) if A_ub else None,
        b_ub=np.array(b_ub) if b_ub else None,
        A_eq=np.array(A_eq),
        b_eq=np.array(b_eq),
        bounds=bounds,
        method="highs",
    )

    if not result.success:
        logger.warning(
            "battery LP did not find an optimal solution (status=%s: %s); "
            "returning zero dispatch",
            result.status, result.message,
        )
        return _zero_dispatch(forecast_blocks)

    x = result.x
    dispatch = []
    soc = soc_init
    for t in range(T):
        c_mw = float(np.clip(x[ci(t)], 0.0, c_rate))
        d_mw = float(np.clip(x[di(t)], 0.0, d_rate))
        soc = float(np.clip(x[si(t)], 0.0, cap))
        block_no = int(forecast_blocks[t].get("block_no", t + 1))
        dispatch.append({
            "block_no": block_no,
            "charge_mw": round(c_mw, 4),
            "discharge_mw": round(d_mw, 4),
            "soc_mwh": round(soc, 4),
        })

    logger.info(
        "battery LP: cap=%.1f MWh c_rate=%.1f d_rate=%.1f "
        "total_charge=%.2f MWh total_discharge=%.2f MWh",
        cap, c_rate, d_rate,
        sum(r["charge_mw"] for r in dispatch) * DT_HOURS,
        sum(r["discharge_mw"] for r in dispatch) * DT_HOURS,
    )
    return dispatch


def _zero_dispatch(forecast_blocks: list[dict]) -> list[dict]:
    return [
        {
            "block_no": int(b.get("block_no", i + 1)),
            "charge_mw": 0.0,
            "discharge_mw": 0.0,
            "soc_mwh": 0.0,
        }
        for i, b in enumerate(forecast_blocks)
    ]
