from datetime import date
from backend.core.config import get_settings, load_plants_config
from backend.modules.dsm.config_loader import DSMRuleConfig

def test_settings_loaded():
    settings = get_settings()
    assert settings.dsm_rule_config is not None
    assert settings.pipeline_api_key is not None

def test_plants_config_loaded():
    plants = load_plants_config()
    assert len(plants) == 4
    plant_ids = [p['id'] for p in plants]
    assert 'GJ_SOLAR_A' in plant_ids
    assert 'GJ_WIND_C' in plant_ids

def test_dsm_rules_x_trajectory():
    dsm_cfg = DSMRuleConfig('config/dsm_rules_2026.yaml')
    
    # Check April 2026 -> X=1.00
    p1 = dsm_cfg.get_params_for_date(date(2026, 4, 1))
    assert p1['x'] == 1.00
    assert p1['solar_band'] == 0.10
    assert p1['wind_band'] == 0.15
    
    # Check Oct 2027 -> X=0.75
    p2 = dsm_cfg.get_params_for_date(date(2027, 10, 15))
    assert p2['x'] == 0.75
    assert p2['solar_band'] == 0.08
    
    # Check Apr 2031 -> X=0.00
    p3 = dsm_cfg.get_params_for_date(date(2031, 4, 1))
    assert p3['x'] == 0.00
    assert p3['solar_band'] == 0.05

def test_frequency_multipliers():
    dsm_cfg = DSMRuleConfig('config/dsm_rules_2026.yaml')
    
    # Low frequency (< 49.90 Hz) -> multiplier = 2.0
    assert dsm_cfg.get_frequency_multiplier(49.85, is_over_injection=False) == 2.0
    
    # Normal frequency (49.95 - 50.03 Hz) -> multiplier = 1.0
    assert dsm_cfg.get_frequency_multiplier(50.00, is_over_injection=False) == 1.0
    
    # High frequency (>= 50.05 Hz) + Over-injection -> 0.0 (unpaid)
    assert dsm_cfg.get_frequency_multiplier(50.06, is_over_injection=True) == 0.0
