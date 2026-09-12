from datetime import date
from backend.modules.dsm.engine import DSMEngine
from backend.modules.dsm.pooling import (
    compute_pooled_deviation,
    compute_pooling_benefit,
)

def test_compute_pooled_deviation():
    # Solar actual=40, sch=30 (+10 MW deviation)
    # Wind actual=20, sch=30 (-10 MW deviation)
    # Net deviation = 0 MW!
    actuals = {'solar_1': 40.0, 'wind_1': 20.0}
    schedules = {'solar_1': 30.0, 'wind_1': 30.0}
    
    dev = compute_pooled_deviation(actuals, schedules, pool_avc_mw=100.0, x=1.0)
    assert dev == 0.0

def test_compute_pooling_benefit():
    dsm_engine = DSMEngine('config/dsm_rules_2026.yaml', date(2026, 4, 1))
    plants_data = [
        {
            'plant_id': 'GJ_SOLAR_A',
            'asset_type': 'solar',
            'avc_mw': 50.0,
            'quantile_forecasts': {0.1: 30.0, 0.5: 45.0, 0.9: 50.0},
            'schedule_mw': 35.0,
        },
        {
            'plant_id': 'GJ_WIND_C',
            'asset_type': 'wind',
            'avc_mw': 40.0,
            'quantile_forecasts': {0.1: 15.0, 0.5: 25.0, 0.9: 35.0},
            'schedule_mw': 35.0,
        }
    ]
    
    result = compute_pooling_benefit(plants_data, dsm_engine, ncd=450.0, freq_hz=50.0)
    assert 'individual_total_inr' in result
    assert 'pooled_total_inr' in result
    assert 'savings_pct' in result
    assert result['pooled_total_inr'] <= result['individual_total_inr']
