"""Physics guard tests for the wind power curve engine.

These tests encode what must never regress:
1. The power curve is exactly zero below cut-in and above cut-out.
2. The power curve is exactly nameplate at rated speed.
3. The ramp zone is monotonically increasing (no negative slope).
4. Hub-wind estimation uses the highest available mast height.
5. The Hellmann extrapolation is physically plausible (hub wind > 10m wind).
6. Uncertainty is zero at the flat-top (rated) and cut-out (zero) regions.
7. A full day produces exactly 96 blocks.
8. Wind generates at night -- the key regression guard against the solar fallback.
9. All P50 values are within nameplate.
10. Quantile ordering is preserved everywhere.
"""
from __future__ import annotations

import pytest

from backend.modules.forecast.physics import (
    WindPhysicsEngine,
    hub_wind_speed,
    power_curve_mw,
    power_curve_slope,
    uncertainty_band,
    swept_area_m2,
    _DEFAULT_CUT_IN_MS,
    _DEFAULT_RATED_MS,
    _DEFAULT_CUT_OUT_MS,
)

AVC_MW = 40.0
PLANT = {
    "id": "GJ_WIND_C",
    "type": "wind",
    "avc_mw": AVC_MW,
    "hub_height_m": 120.0,
    "rotor_diameter_m": 130.0,
    "power_curve": "care_wind_farm_a_fitted",
}

# ────────────────────────────────────────────── power curve primitives ────────

class TestPowerCurve:
    def test_zero_below_cut_in(self):
        for u in [0.0, 1.0, 2.9]:
            assert power_curve_mw(u, AVC_MW) == 0.0, f"expected 0 at u={u}"

    def test_rated_at_rated_speed(self):
        assert power_curve_mw(_DEFAULT_RATED_MS, AVC_MW) == pytest.approx(AVC_MW, rel=1e-6)

    def test_just_above_rated_still_rated(self):
        assert power_curve_mw(_DEFAULT_RATED_MS + 1.0, AVC_MW) == pytest.approx(AVC_MW)

    def test_zero_above_cut_out(self):
        for u in [25.0, 26.0, 35.0]:
            assert power_curve_mw(u, AVC_MW) == 0.0, f"expected 0 at u={u}"

    def test_ramp_zone_monotone(self):
        """Power must be non-decreasing from cut-in to rated speed."""
        speeds = [_DEFAULT_CUT_IN_MS + i * 0.5 for i in range(20)]
        powers = [power_curve_mw(u, AVC_MW) for u in speeds]
        for i in range(1, len(powers)):
            assert powers[i] >= powers[i - 1] - 1e-9, \
                f"power decreased at u={speeds[i]:.1f}: {powers[i-1]:.3f} → {powers[i]:.3f}"

    def test_positive_in_ramp_zone(self):
        u = (_DEFAULT_CUT_IN_MS + _DEFAULT_RATED_MS) / 2.0
        assert power_curve_mw(u, AVC_MW) > 0.0

    def test_within_nameplate(self):
        for u in range(0, 30):
            p = power_curve_mw(float(u), AVC_MW)
            assert 0.0 <= p <= AVC_MW + 1e-9, f"out of range at u={u}: {p}"

    def test_swept_area(self):
        # 130 m rotor → radius 65 m → π × 65² ≈ 13,273 m²
        area = swept_area_m2(130.0)
        assert 13_000 < area < 13_500


# ──────────────────────────────────────────── hub wind speed estimation ───────

class TestHubWindSpeed:
    def test_uses_120m_directly_for_120m_hub(self):
        u = hub_wind_speed(ws_10m=5.0, ws_80m=7.0, ws_120m=9.0, hub_height_m=120.0)
        assert u == pytest.approx(9.0)

    def test_falls_back_to_80m_when_120m_missing(self):
        u = hub_wind_speed(ws_10m=5.0, ws_80m=7.5, ws_120m=None, hub_height_m=120.0)
        # Hellmann: u(120) = 7.5 × (120/80)^0.143 ≈ 7.5 × 1.055 ≈ 7.91
        assert u is not None
        assert 7.0 < u < 9.0

    def test_falls_back_to_10m_when_others_missing(self):
        u = hub_wind_speed(ws_10m=5.0, ws_80m=None, ws_120m=None, hub_height_m=120.0)
        # Hellmann: u(120) = 5.0 × (120/10)^0.143 ≈ 5.0 × 1.368 ≈ 6.84
        assert u is not None
        assert u > 5.0  # hub wind > 10m wind for flat terrain

    def test_returns_none_when_all_missing(self):
        u = hub_wind_speed(ws_10m=None, ws_80m=None, ws_120m=None)
        assert u is None

    def test_hub_wind_exceeds_10m_wind(self):
        """Wind speed increases with height over open terrain."""
        u_10m = 6.0
        u_hub = hub_wind_speed(ws_10m=u_10m, ws_80m=None, ws_120m=None, hub_height_m=80.0)
        assert u_hub > u_10m


# ──────────────────────────────────────────────── uncertainty band ────────────

class TestUncertaintyBand:
    def test_p10_less_than_p50(self):
        u = 8.0  # ramp zone -- slope is steep
        p50 = power_curve_mw(u, AVC_MW)
        p10, p90 = uncertainty_band(p50, u, AVC_MW, sigma_u=1.0)
        assert p10 <= p50

    def test_p90_greater_than_p50(self):
        u = 8.0
        p50 = power_curve_mw(u, AVC_MW)
        p10, p90 = uncertainty_band(p50, u, AVC_MW, sigma_u=1.0)
        assert p90 >= p50

    def test_band_widens_with_sigma(self):
        u = 8.0
        p50 = power_curve_mw(u, AVC_MW)
        p10_narrow, p90_narrow = uncertainty_band(p50, u, AVC_MW, sigma_u=0.5)
        p10_wide, p90_wide = uncertainty_band(p50, u, AVC_MW, sigma_u=2.0)
        assert p10_wide <= p10_narrow
        assert p90_wide >= p90_narrow

    def test_band_within_nameplate(self):
        for u in [4.0, 8.0, 12.0]:
            p50 = power_curve_mw(u, AVC_MW)
            p10, p90 = uncertainty_band(p50, u, AVC_MW, sigma_u=2.0)
            assert 0.0 <= p10 <= AVC_MW
            assert 0.0 <= p90 <= AVC_MW

    def test_slope_zero_above_cut_out(self):
        """Above cut-out, output is 0 and the slope is 0 -- band stays at 0."""
        slope = power_curve_slope(26.0, AVC_MW)
        assert abs(slope) < 1e-6


# ──────────────────────────────────────────── full engine integration ─────────

def _make_weather(num_blocks: int = 96, wind_speed_ms: float = 9.0) -> dict:
    """Synthetic flat wind-day: 9 m/s at all mast heights all day."""
    return {
        b: {
            "wind_speed_10m": wind_speed_ms,
            "wind_speed_80m": wind_speed_ms * 1.08,
            "wind_speed_120m": wind_speed_ms * 1.12,
            # Solar variables present but should be ignored for wind
            "shortwave_radiation": 600.0 if 24 <= b <= 72 else 0.0,
        }
        for b in range(1, num_blocks + 1)
    }


class TestWindPhysicsEngine:
    @pytest.fixture(scope="class")
    def engine(self):
        return WindPhysicsEngine()

    @pytest.fixture(scope="class")
    def forecast(self, engine):
        return engine.generate_forecast(PLANT, "2026-09-13", 96, weather=_make_weather())

    def test_full_day_is_96_blocks(self, forecast):
        assert len(forecast) == 96

    def test_wind_generates_at_night(self, forecast):
        """KEY GUARD: wind ≠ solar. Night blocks must have non-zero output.

        Solar would zero everything from block 1–24 (00:00–06:00 IST).
        A 9 m/s wind farm above cut-in should produce ~50% of rated all night.
        """
        night_blocks = [b for b in forecast if b["block_no"] <= 24]
        night_p50s = [b["p50"] for b in night_blocks]
        assert all(p > 0.0 for p in night_p50s), \
            f"night blocks show zero: {[p for p in night_p50s if p == 0.0]}"

    def test_model_name_is_wind_physics(self, forecast):
        assert all(b["model_name"] == "wind_physics_iec" for b in forecast)

    def test_output_within_nameplate(self, forecast):
        for b in forecast:
            assert 0.0 <= b["p50"] <= AVC_MW + 1e-6, \
                f"block {b['block_no']} p50={b['p50']} exceeds nameplate"

    def test_quantiles_ordered(self, forecast):
        """p05 ≤ p10 ≤ p25 ≤ p50 ≤ p75 ≤ p90 ≤ p95 at every block."""
        order = ("p05", "p10", "p25", "p50", "p75", "p90", "p95")
        for b in forecast:
            vals = [b[q] for q in order]
            assert vals == sorted(vals), \
                f"block {b['block_no']} quantiles not ordered: {dict(zip(order, vals))}"

    def test_no_weather_gives_zero_p50(self, engine):
        """Engine must not crash or fabricate data when weather is empty."""
        blocks = engine.generate_forecast(PLANT, "2026-09-13", 96, weather={})
        p50s = [b["p50"] for b in blocks]
        assert all(p == 0.0 for p in p50s)

    def test_high_wind_gives_rated_output(self, engine):
        """15 m/s > u_rated (12.5 m/s) → all blocks at nameplate MW."""
        weather = _make_weather(wind_speed_ms=15.0)
        blocks = engine.generate_forecast(PLANT, "2026-09-13", 96, weather=weather)
        p50s = [b["p50"] for b in blocks]
        assert all(abs(p - AVC_MW) < 1e-6 for p in p50s), \
            f"not all blocks at rated: min={min(p50s):.3f}"

    def test_storm_speed_gives_zero(self, engine):
        """30 m/s > cut-out (25 m/s) → turbine trips, output = 0."""
        weather = _make_weather(wind_speed_ms=30.0)
        blocks = engine.generate_forecast(PLANT, "2026-09-13", 96, weather=weather)
        p50s = [b["p50"] for b in blocks]
        assert all(p == 0.0 for p in p50s)
