import numpy as np
import math
import hashlib
from typing import List, Dict

class MockForecastEngine:
    """Mock forecast engine generating synthetic probabilistic forecasts."""
    
    def generate_forecast(self, plant: Dict, date_str: str, num_blocks: int = 96) -> List[Dict]:
        plant_id = plant.get('plant_id', 'unknown')
        avc_mw = plant.get('avc_mw', 100.0)
        asset_type = plant.get('asset_type', 'solar').lower()
        
        # Seed for reproducibility based on plant_id and date
        seed_str = f"{plant_id}_{date_str}"
        seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        
        forecasts = []
        
        for block in range(1, num_blocks + 1):
            if asset_type == 'solar':
                if 25 <= block <= 72:
                    base_mw = avc_mw * math.sin(math.pi * (block - 24) / 48)
                else:
                    base_mw = 0.0
            else:
                # Wind profile
                base_mw = avc_mw * 0.35 * (1 + 0.3 * math.sin(2 * math.pi * block / 96))
                
            # Add random noise for base
            noise = rng.normal(0, avc_mw * 0.05)
            p50 = max(0.0, min(avc_mw, base_mw + noise))
            
            # Spread factor
            spread_factor = 0.2 if asset_type == 'solar' else 0.4
            
            quantiles = {}
            for q in [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]:
                if q == 0.50:
                    val = p50
                else:
                    val = p50 * (1 + spread_factor * (q - 0.5))
                quantiles[q] = max(0.0, min(avc_mw, val))
                
            # Ensure monotonic ordering
            q_keys = sorted(quantiles.keys())
            for i in range(1, len(q_keys)):
                if quantiles[q_keys[i]] < quantiles[q_keys[i-1]]:
                    quantiles[q_keys[i]] = quantiles[q_keys[i-1]]
                    
            hour = (block - 1) // 4
            minute = ((block - 1) % 4) * 15
            valid_time = f"{date_str}T{hour:02d}:{minute:02d}:00Z"
            
            block_data = {
                'block_no': block,
                'valid_time': valid_time,
                'p05': quantiles[0.05],
                'p10': quantiles[0.10],
                'p25': quantiles[0.25],
                'p50': quantiles[0.50],
                'p75': quantiles[0.75],
                'p90': quantiles[0.90],
                'p95': quantiles[0.95],
                'model_name': 'mock'
            }
            forecasts.append(block_data)
            
        return forecasts
