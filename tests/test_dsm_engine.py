import pytest
from datetime import date
from backend.modules.dsm.engine import DSMEngine

def test_dsm_deviation_pct_formula():
    engine = DSMEngine('config/dsm_rules_2026.yaml', date(2026, 4, 1))
    # At 2026-04-01, X=1.00 -> denominator = 1.0 * AvC + 0 = AvC
    # Actual=45, Schedule=40, AvC=50 -> (45-40)/50 = 5/50 = +10%
    dev = engine.compute_deviation_pct(actual_mw=45.0, schedule_mw=40.0, avc_mw=50.0)
    assert pytest.approx(dev, 0.01) == 10.0

def test_dsm_within_tolerance_zero_penalty():
    engine = DSMEngine('config/dsm_rules_2026.yaml', date(2026, 4, 1))
    # Solar band is +-10% (0.10). Deviation of 8% should yield 0 penalty
    # Actual=44, Schedule=40, AvC=50 -> 4/50 = 8% <= 10%
    penalty = engine.compute_block_penalty(
        actual_mw=44.0,
        schedule_mw=40.0,
        avc_mw=50.0,
        freq_hz=50.0,
        ncd_inr_per_mwh=450.0,
        asset_type='solar'
    )
    assert penalty == 0.0

def test_dsm_outside_tolerance_penalty():
    engine = DSMEngine('config/dsm_rules_2026.yaml', date(2026, 4, 1))
    # Actual=50, Schedule=40, AvC=50 -> (50-40)/50 = 20% > 10% tolerance
    # Deviation MW = 10 MW -> in 15 mins = 2.5 MWh
    # Frequency 50.0 Hz (normal) -> multiplier = 1.0
    # Penalty = 2.5 MWh * 450 INR/MWh * 1.0 = 1125 INR
    penalty = engine.compute_block_penalty(
        actual_mw=50.0,
        schedule_mw=40.0,
        avc_mw=50.0,
        freq_hz=50.0,
        ncd_inr_per_mwh=450.0,
        asset_type='solar'
    )
    assert pytest.approx(penalty, 0.1) == 1125.0

def test_dsm_high_frequency_over_injection_zero_payment():
    engine = DSMEngine('config/dsm_rules_2026.yaml', date(2026, 4, 1))
    # Over-injection at freq >= 50.05 Hz -> 0.0
    penalty = engine.compute_block_penalty(
        actual_mw=55.0,
        schedule_mw=40.0,
        avc_mw=50.0,
        freq_hz=50.06,
        ncd_inr_per_mwh=450.0,
        asset_type='solar'
    )
    assert penalty == 0.0

def test_expected_penalty_across_quantiles():
    engine = DSMEngine('config/dsm_rules_2026.yaml', date(2026, 4, 1))
    q_forecasts = {
        0.10: 35.0,
        0.50: 45.0,
        0.90: 55.0
    }
    exp_penalty = engine.compute_expected_penalty(
        quantile_forecasts=q_forecasts,
        schedule_mw=40.0,
        avc_mw=50.0,
        freq_hz=50.0,
        ncd=450.0,
        asset_type='solar'
    )
    assert exp_penalty >= 0.0
