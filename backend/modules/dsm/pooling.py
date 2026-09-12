from typing import List, Dict

def compute_pooled_deviation(plants_actual: Dict[str, float], plants_schedule: Dict[str, float], pool_avc_mw: float, x: float) -> float:
    """Compute pooled deviation percentage across multiple plants."""
    total_actual = sum(plants_actual.values())
    total_schedule = sum(plants_schedule.values())
    
    denom = (x * pool_avc_mw) + ((1.0 - x) * total_schedule)
    if denom == 0.0:
        return 0.0
        
    return 100.0 * (total_actual - total_schedule) / denom

def compute_pooling_benefit(plants_data: List[Dict], dsm_engine, ncd: float, freq_hz: float) -> Dict:
    """Compute pooling benefits across plants."""
    individual_total_inr = 0.0
    per_plant = []
    
    # 1. Compute individual penalties
    for plant in plants_data:
        plant_id = plant['plant_id']
        asset_type = plant['asset_type']
        avc_mw = plant['avc_mw']
        schedule_mw = plant['schedule_mw']
        quantiles = plant['quantile_forecasts']
        
        expected_penalty = dsm_engine.compute_expected_penalty(quantiles, schedule_mw, avc_mw, freq_hz, ncd, asset_type)
        individual_total_inr += expected_penalty
        
        per_plant.append({
            'plant_id': plant_id,
            'individual_inr': expected_penalty
        })
        
    # 2. Compute pooled penalty by aggregating forecasts and schedules
    # Assuming quantiles map identically across plants (perfect correlation for simplicity in mock)
    # We aggregate each quantile
    if not plants_data:
        return {
            'individual_total_inr': 0.0,
            'pooled_total_inr': 0.0,
            'savings_pct': 0.0,
            'per_plant': []
        }
        
    base_quantiles = plants_data[0]['quantile_forecasts'].keys()
    pooled_quantiles = {}
    
    pool_avc_mw = sum(p['avc_mw'] for p in plants_data)
    pool_schedule_mw = sum(p['schedule_mw'] for p in plants_data)
    
    for q in base_quantiles:
        pooled_quantiles[q] = sum(p['quantile_forecasts'].get(q, 0.0) for p in plants_data)
        
    # Evaluate pooled penalty (treating pool as a combined entity, we can approximate it as solar/wind mix, 
    # but let's just use the engine with a generic type or the primary type)
    # We will use 'solar' as a default if mixed, or whatever the first plant is.
    primary_asset_type = plants_data[0]['asset_type']
    
    pooled_total_inr = dsm_engine.compute_expected_penalty(
        pooled_quantiles, pool_schedule_mw, pool_avc_mw, freq_hz, ncd, primary_asset_type
    )
    
    savings = max(0.0, individual_total_inr - pooled_total_inr)
    savings_pct = (savings / individual_total_inr * 100.0) if individual_total_inr > 0 else 0.0
    
    return {
        'individual_total_inr': individual_total_inr,
        'pooled_total_inr': pooled_total_inr,
        'savings_inr': savings,
        'savings_pct': savings_pct,
        'per_plant': per_plant
    }

def allocate_pool_savings(individual_penalties: Dict[str, float], pooled_total: float) -> Dict[str, float]:
    """Allocate pooled costs to individual plants pro-rata based on individual penalties."""
    sum_individual = sum(individual_penalties.values())
    allocation = {}
    
    for plant_id, penalty in individual_penalties.items():
        if sum_individual == 0:
            allocation[plant_id] = 0.0
        else:
            allocation[plant_id] = pooled_total * (penalty / sum_individual)
            
    return allocation
