from typing import List, Dict

class MockScheduleOptimizer:
    """Mock schedule optimizer and battery dispatcher."""
    
    def optimize_day_ahead(self, forecast_blocks: List[Dict], avc_mw: float, dsm_engine, ncd: float = 450.0, freq_hz: float = 50.0, asset_type: str = 'solar', **kwargs) -> Dict:
        optimised_schedule = []
        naive_schedule = []
        battery_dispatch = []
        
        naive_total_inr = 0.0
        optimised_total_inr = 0.0
        action_cards = []
        
        for block_data in forecast_blocks:
            block_no = block_data['block_no']
            
            quantiles = {
                0.05: block_data['p05'],
                0.10: block_data['p10'],
                0.25: block_data['p25'],
                0.50: block_data['p50'],
                0.75: block_data['p75'],
                0.90: block_data['p90'],
                0.95: block_data['p95']
            }
            
            p50 = quantiles[0.50]
            naive_schedule.append(p50)
            
            # Try a small grid of schedule values
            candidates = [quantiles[0.10], quantiles[0.25], quantiles[0.50], quantiles[0.75], quantiles[0.90]]
            
            best_penalty = float('inf')
            best_schedule = p50
            
            for cand in candidates:
                expected_penalty = dsm_engine.compute_expected_penalty(
                    quantiles, cand, avc_mw, freq_hz, ncd, asset_type
                )
                if expected_penalty < best_penalty:
                    best_penalty = expected_penalty
                    best_schedule = cand
                    
            optimised_schedule.append(best_schedule)
            
            # Naive penalty
            naive_pen = dsm_engine.compute_expected_penalty(
                quantiles, p50, avc_mw, freq_hz, ncd, asset_type
            )
            naive_total_inr += naive_pen
            optimised_total_inr += best_penalty
            
            battery_dispatch.append({
                'block_no': block_no,
                'charge_mw': 0.0,
                'discharge_mw': 0.0,
                'soc_mwh': 0.0
            })
            
            # Generate action cards
            if p50 > avc_mw * 0.9:
                action_cards.append({
                    'type': 'curtailment',
                    'block_no': block_no,
                    'mw': round(p50 - avc_mw * 0.9, 2),
                    'reason': 'High generation predicted; risk of over-injection.',
                    'inr_impact': round(best_penalty, 2)
                })
            elif p50 < avc_mw * 0.1 and asset_type == 'solar' and (25 <= block_no <= 72):
                action_cards.append({
                    'type': 'reserve_flag',
                    'block_no': block_no,
                    'mw': round(avc_mw * 0.1 - p50, 2),
                    'reason': 'Daytime low generation; consider deploying reserves if available.',
                    'inr_impact': round(best_penalty, 2)
                })
                
        savings_inr = naive_total_inr - optimised_total_inr
        savings_pct = (savings_inr / naive_total_inr * 100.0) if naive_total_inr > 0 else 0.0
        
        return {
            'optimised_schedule': optimised_schedule,
            'naive_schedule': naive_schedule,
            'battery_dispatch': battery_dispatch,
            'naive_total_inr': naive_total_inr,
            'optimised_total_inr': optimised_total_inr,
            'savings_inr': savings_inr,
            'savings_pct': savings_pct,
            'action_cards': action_cards
        }
