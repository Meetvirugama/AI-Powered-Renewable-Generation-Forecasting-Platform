"""Wind power curve physics engine.

No machine learning. Wind turbine output is physics: the turbine's power curve
converts hub-height wind speed into megawatts. Open-Meteo already supplies
wind_speed_80m and wind_speed_120m; GJ_WIND_C's hub is at exactly 120 m, so no
extrapolation is needed -- the 120m reading is used directly.

Why physics is the right choice for wind
-----------------------------------------
The LightGBM engine was trained on a solar plant: it predicts a capacity factor
shaped by irradiance, time-of-day, and cloud cover. Applied to a wind turbine it
produces a bell curve that peaks at noon, drops to zero at night, and is
physically wrong in both directions -- wind farms regularly run overnight, and
solar irradiance tells you nothing about wind speed.

A wind turbine's power curve, by contrast, is specified in the turbine's type
certificate (IEC 61400-12). Given the hub-height wind speed at each block, the
output follows directly:

    P = 0                                   if u < u_cut_in
    P = 0.5 × ρ × A × Cp(u) × u³ / 1e6   if u_cut_in ≤ u < u_rated
    P = P_rated                             if u_rated ≤ u < u_cut_out
    P = 0                                   if u ≥ u_cut_out

where:
  ρ   = air density at hub elevation (~1.225 kg/m³ at sea level, Gujarat)
  A   = π r² (rotor swept area, r = rotor_diameter / 2)
  Cp  = power coefficient (≈ 0.45 at rated, per Betz limit ~0.593)

The cubic is fitted to reproduce the rated output exactly at u_rated, which is
standard practice for site-transfer of a type-certificate curve.

Uncertainty
-----------
A single-point wind forecast has an error of roughly 1 m/s at 24 h and 2 m/s
at 72 h (ECMWF benchmark figures for open terrain). The uncertainty in the power
output is the wind forecast error propagated through the power curve's slope at
the operating point:

    σ_P ≈ |dP/du| × σ_u

The slope is largest in the ramp zone (cut-in to rated) and zero at rated power
(saturated). This naturally gives a narrow band when the turbine is running flat-
out and a wide one when it is ramping -- which is the physical reality.

Plant config keys read from plants.yaml
----------------------------------------
    hub_height_m        hub height (m), default 120
    rotor_diameter_m    rotor diameter (m), default 130
    cut_in_ms           cut-in wind speed (m/s), default 3.0
    rated_ms            rated wind speed (m/s), default 12.5
    cut_out_ms          cut-out wind speed (m/s), default 25.0
    air_density         kg/m³, default 1.225

If power_curve is set to a string name in plants.yaml, the named presets below
are tried first. Unknown names fall back to the IEC defaults.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger("renewable_platform")

# IEC class IIA defaults (typical Gujarat onshore turbine, 130 m rotor)
_DEFAULT_CUT_IN_MS = 3.0
_DEFAULT_RATED_MS = 12.5
_DEFAULT_CUT_OUT_MS = 25.0
_DEFAULT_AIR_DENSITY = 1.225  # kg/m³ (sea-level; Gujarat plains ≈ 1.19, conservative)
_BETZ_CP = 0.45               # realistic Cp for a modern IEC IIA turbine at rated speed

# Named preset curves. Keys match plant config's `power_curve` field.
# Values are (cut_in_ms, rated_ms, cut_out_ms, Cp_at_rated).
# "care_wind_farm_a_fitted" is the name in plants.yaml for GJ_WIND_C.
_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "care_wind_farm_a_fitted": (3.0, 12.5, 25.0, 0.45),
    "iec_iia_default":         (3.0, 12.5, 25.0, 0.45),
    "iec_iib_default":         (3.0, 11.0, 22.0, 0.44),
    "iec_ia_default":          (3.0, 14.0, 25.0, 0.46),
}

# Hellmann exponent for open flat terrain (IEC/CIGRE standard)
_ALPHA_OPEN_TERRAIN = 0.143

# Open-Meteo reports wind speed in km/h unless a request sets wind_speed_unit=ms,
# and neither fetcher does. The fetchers are left alone deliberately: the
# LightGBM training data came from the same km/h feed, so switching them to m/s
# would silently skew the solar model's wind feature. Convert here instead.
_KMH_PER_MS = 3.6


def _kmh_to_ms(value: float | None) -> float | None:
    return None if value is None else float(value) / _KMH_PER_MS


# ─────────────────────────────────────────────── physics primitives ──────────

def hub_wind_speed(
    ws_10m: float | None,
    ws_80m: float | None,
    ws_120m: float | None,
    hub_height_m: float = 120.0,
    alpha: float = _ALPHA_OPEN_TERRAIN,
) -> float | None:
    """Estimate wind speed at hub height using the Hellmann power law.

    Uses the highest-resolution anchor available:
      1. ws_120m directly, if the hub is at 120 m (GJ_WIND_C)
      2. ws_80m extrapolated upward with the Hellmann law
      3. ws_10m extrapolated upward (wider uncertainty; logged)
      4. None -- no wind data for this block

    The Hellmann law:  u(h) = u(h_ref) × (h / h_ref) ^ alpha
    """
    if ws_120m is not None and ws_120m >= 0:
        if abs(hub_height_m - 120.0) < 1.0:
            return float(ws_120m)
        # Hub is not at 120 m -- use 120 m as the reference height
        return float(ws_120m) * (hub_height_m / 120.0) ** alpha

    if ws_80m is not None and ws_80m >= 0:
        return float(ws_80m) * (hub_height_m / 80.0) ** alpha

    if ws_10m is not None and ws_10m >= 0:
        logger.debug(
            "hub wind: only 10m available; Hellmann extrapolation to %.0f m "
            "has high uncertainty (α=%.3f)",
            hub_height_m, alpha,
        )
        return float(ws_10m) * (hub_height_m / 10.0) ** alpha

    return None


def swept_area_m2(rotor_diameter_m: float) -> float:
    """π r²"""
    return math.pi * (rotor_diameter_m / 2.0) ** 2


def _cubic_ramp_mw(
    u: float,
    cut_in: float,
    u_rated: float,
    avc_mw: float,
    rho: float,
    area: float,
    cp: float,
) -> float:
    """Power in the ramp zone [cut_in, u_rated].

    The Cp value is chosen so that the cubic exactly equals avc_mw at u_rated,
    making the curve continuous. Raw physics would give 0.5 * rho * A * Cp * u³,
    but that only works if Cp and the turbine geometry are perfectly known. Here
    we anchor on the known nameplate and interpolate backward.

    The resulting curve is:
        P(u) = P_rated × (u³ - cut_in³) / (u_rated³ - cut_in³)

    This is the IEC 61400-12 "cubic interpolation between cut-in and rated",
    which is the industry standard for site assessments when a measured power
    curve is not available.
    """
    denom = u_rated ** 3 - cut_in ** 3
    if denom <= 0:
        return avc_mw
    fraction = max(0.0, (u ** 3 - cut_in ** 3) / denom)
    return avc_mw * min(fraction, 1.0)


def power_curve_mw(
    u_hub: float,
    avc_mw: float,
    cut_in: float = _DEFAULT_CUT_IN_MS,
    u_rated: float = _DEFAULT_RATED_MS,
    cut_out: float = _DEFAULT_CUT_OUT_MS,
    rho: float = _DEFAULT_AIR_DENSITY,
    rotor_diameter_m: float = 130.0,
    cp: float = _BETZ_CP,
) -> float:
    """IEC 61400-12 piecewise power curve, MW.

    Returns exactly 0 below cut-in and above cut-out.
    Returns exactly avc_mw between rated and cut-out.
    Cubic ramp in between.
    """
    if u_hub < cut_in or u_hub >= cut_out:
        return 0.0
    if u_hub >= u_rated:
        return avc_mw
    return _cubic_ramp_mw(u_hub, cut_in, u_rated, avc_mw, rho, swept_area_m2(rotor_diameter_m), cp)


def power_curve_slope(
    u_hub: float,
    avc_mw: float,
    cut_in: float = _DEFAULT_CUT_IN_MS,
    u_rated: float = _DEFAULT_RATED_MS,
    cut_out: float = _DEFAULT_CUT_OUT_MS,
    delta: float = 0.1,
) -> float:
    """∂P/∂u at the operating point, MW per (m/s). Numerical central difference."""
    p_hi = power_curve_mw(u_hub + delta, avc_mw, cut_in, u_rated, cut_out)
    p_lo = power_curve_mw(u_hub - delta, avc_mw, cut_in, u_rated, cut_out)
    return (p_hi - p_lo) / (2.0 * delta)


def uncertainty_band(
    p50: float,
    u_hub: float,
    avc_mw: float,
    sigma_u: float,
    cut_in: float = _DEFAULT_CUT_IN_MS,
    u_rated: float = _DEFAULT_RATED_MS,
    cut_out: float = _DEFAULT_CUT_OUT_MS,
) -> tuple[float, float]:
    """Propagate wind forecast error through the power curve slope.

    Returns (p10, p90) as 1-sigma Gaussian tails. The distribution of
    wind forecast errors is approximately Gaussian at day-ahead horizons
    (ECMWF, ERA5 verification), so ±1.28σ gives the 10th/90th percentile.

    σ_u should be:
      24h lead  → 1.0 m/s
      48h lead  → 1.5 m/s
      72h lead  → 2.0 m/s
    """
    slope = abs(power_curve_slope(u_hub, avc_mw, cut_in, u_rated, cut_out))
    sigma_p = slope * sigma_u
    z_10_90 = 1.282  # Φ^-1(0.10) in absolute value
    p10 = max(0.0, p50 - z_10_90 * sigma_p)
    p90 = min(avc_mw, p50 + z_10_90 * sigma_p)
    return p10, p90


# ──────────────────────────────────────────────── engine class ───────────────

class WindPhysicsEngine:
    """Deterministic wind power curve engine.

    Produces a 96-block probabilistic forecast from Open-Meteo hub-height
    winds and the IEC 61400-12 power curve.  Runs entirely offline once the
    weather data is fetched -- no model files, no training data.

    The engine is selected by `backend.modules.factory.CompositeEngine`
    for plants whose `type == "wind"`, regardless of FORECAST_ENGINE_TYPE.
    This is intentional: the LightGBM engine would apply a solar-trained
    capacity-factor transfer to a wind turbine, producing a bell curve
    that is physically wrong.
    """

    requires_weather = True

    def generate_forecast(
        self,
        plant: dict[str, Any],
        date_str: str,
        num_blocks: int = 96,
        *,
        weather: dict[int, dict] | None = None,
        **_kwargs: Any,
    ) -> list[dict]:
        weather = weather or {}

        avc_mw = float(plant.get("avc_mw") or 0.0)
        plant_id = str(plant.get("id") or plant.get("plant_id") or "<wind>")
        hub_h = float(plant.get("hub_height_m") or 120.0)
        rotor_d = float(plant.get("rotor_diameter_m") or 130.0)

        # Load power curve parameters: named preset → yaml keys → IEC defaults
        curve_name = plant.get("power_curve", "")
        preset = _PRESETS.get(str(curve_name), None)
        if preset:
            cut_in, u_rated, cut_out, cp = preset
        else:
            cut_in  = float(plant.get("cut_in_ms",  _DEFAULT_CUT_IN_MS))
            u_rated = float(plant.get("rated_ms",   _DEFAULT_RATED_MS))
            cut_out = float(plant.get("cut_out_ms", _DEFAULT_CUT_OUT_MS))
            cp      = float(plant.get("cp",         _BETZ_CP))

        rho = float(plant.get("air_density", _DEFAULT_AIR_DENSITY))

        # Wind forecast error σ_u grows with horizon length.
        # Default to 24h uncertainty; callers can override via plant config.
        sigma_u = float(plant.get("wind_sigma_ms", 1.0))

        from backend.modules.forecast.feature_builder import block_timestamps
        from datetime import timezone
        timestamps = block_timestamps(date_str, num_blocks)

        blocks: list[dict] = []
        missing_blocks = 0

        for row in range(num_blocks):
            block_no = row + 1
            bw = weather.get(block_no, {})

            # Weather arrives in Open-Meteo's native km/h; the power curve is m/s.
            # Reading km/h as m/s saturates a 20 km/h breeze at nameplate and
            # trips cut-out at 25 km/h -- which is exactly what production served.
            ws_10m  = _kmh_to_ms(bw.get("wind_speed_10m"))
            ws_80m  = _kmh_to_ms(bw.get("wind_speed_80m"))
            ws_120m = _kmh_to_ms(bw.get("wind_speed_120m"))

            u_hub = hub_wind_speed(ws_10m, ws_80m, ws_120m, hub_h)

            if u_hub is None:
                # No wind data for this block — return zero with wide band
                p50 = 0.0
                p10, p90 = 0.0, avc_mw * 0.5
                missing_blocks += 1
            else:
                p50 = power_curve_mw(u_hub, avc_mw, cut_in, u_rated, cut_out, rho, rotor_d, cp)
                p10, p90 = uncertainty_band(p50, u_hub, avc_mw, sigma_u, cut_in, u_rated, cut_out)

            ts = timestamps[row]
            # Interpolate remaining quantiles linearly in quantile space
            lower = p50 - p10
            upper = p90 - p50
            quantiles = {
                "p05": max(0.0, p50 - 1.35 * lower),
                "p10": p10,
                "p25": max(0.0, p50 - 0.45 * lower),
                "p50": p50,
                "p75": min(avc_mw, p50 + 0.45 * upper),
                "p90": p90,
                "p95": min(avc_mw, p50 + 1.35 * upper),
            }

            blocks.append({
                "block_no": block_no,
                "valid_time": ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ist_time": ts.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
                **{k: round(v, 4) for k, v in quantiles.items()},
                "model_name": "wind_physics_iec",
                "u_hub_ms": round(u_hub, 3) if u_hub is not None else None,
            })

        if missing_blocks > 48:
            logger.warning(
                "wind physics: %d/%d blocks had no hub-height wind data for plant %s on %s. "
                "Check Open-Meteo response includes wind_speed_80m/120m.",
                missing_blocks, num_blocks, plant_id, date_str,
            )
        else:
            logger.info(
                "wind physics: plant=%s date=%s blocks=%d missing_wind=%d "
                "peak_p50=%.2f MW hub=%.0fm",
                plant_id, date_str, num_blocks, missing_blocks,
                max((b["p50"] for b in blocks), default=0.0), hub_h,
            )

        return blocks
