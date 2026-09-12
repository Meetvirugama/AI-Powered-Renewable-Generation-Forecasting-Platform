from datetime import date
from .config_loader import DSMRuleConfig

class DSMEngine:
    """CERC DSM calculation engine (Seller-Side, Renewable Generator)."""
    
    def __init__(self, config_path: str, rule_date: date):
        self.config = DSMRuleConfig(config_path)
        params = self.config.get_params_for_date(rule_date)
        self.x = params.get('x', 1.0)
        self.solar_band = params.get('solar_band', 0.10)
        self.wind_band = params.get('wind_band', 0.15)

    def compute_deviation_pct(self, actual_mw: float, schedule_mw: float, avc_mw: float) -> float:
        """Compute deviation percentage."""
        denom = (self.x * avc_mw) + ((1.0 - self.x) * schedule_mw)
        if denom == 0.0:
            return 0.0
        return 100.0 * (actual_mw - schedule_mw) / denom

    def compute_block_penalty(self, actual_mw: float, schedule_mw: float, avc_mw: float, freq_hz: float, ncd_inr_per_mwh: float, asset_type: str) -> float:
        """Compute penalty for a single block (in INR)."""
        dev_pct = self.compute_deviation_pct(actual_mw, schedule_mw, avc_mw)
        band = self.solar_band if asset_type.lower() == 'solar' else self.wind_band
        
        # Within tolerance band
        if abs(dev_pct) <= band * 100.0:
            return 0.0
            
        is_over_injection = actual_mw > schedule_mw
        # Over-injection during high frequency -> curtailed unpaid, treated as 0 penalty but generator loses revenue
        # According to requirements: "For over-injection at freq >= 50.05, returns 0.0 (zero payment)"
        # Note: If there's a penalty for over-injection, we multiply by frequency multiplier
        
        multiplier = self.config.get_frequency_multiplier(freq_hz, is_over_injection)
        if multiplier == 0.0:
            return 0.0
            
        # 15-min block => MWh is MW / 4
        deviation_mwh = (actual_mw - schedule_mw) / 4.0
        penalty = abs(deviation_mwh) * ncd_inr_per_mwh * multiplier
        
        return penalty

    def compute_expected_penalty(self, quantile_forecasts: dict[float, float], schedule_mw: float, avc_mw: float, freq_hz: float, ncd: float, asset_type: str) -> float:
        """Compute expected penalty across quantile forecasts."""
        penalties = []
        for q, actual_mw in quantile_forecasts.items():
            penal_val = self.compute_block_penalty(actual_mw, schedule_mw, avc_mw, freq_hz, ncd, asset_type)
            penalties.append(penal_val)
            
        if not penalties:
            return 0.0
        return sum(penalties) / len(penalties)

    def compute_day_penalties(self, block_quantiles: list[dict[float, float]], schedule_per_block: list[float], avc_mw: float, freq_hz: float, ncd: float, asset_type: str) -> list[dict]:
        """Compute penalties for the whole day (96 blocks)."""
        results = []
        for i, (quantiles, schedule) in enumerate(zip(block_quantiles, schedule_per_block)):
            block_no = i + 1
            expected_penalty_inr = self.compute_expected_penalty(quantiles, schedule, avc_mw, freq_hz, ncd, asset_type)
            
            p50_val = quantiles.get(0.5, 0.0)
            p50_penalty_inr = self.compute_block_penalty(p50_val, schedule, avc_mw, freq_hz, ncd, asset_type)
            deviation_pct_at_p50 = self.compute_deviation_pct(p50_val, schedule, avc_mw)
            
            results.append({
                'block_no': block_no,
                'expected_penalty_inr': expected_penalty_inr,
                'p50_penalty_inr': p50_penalty_inr,
                'schedule_mw': schedule,
                'deviation_pct_at_p50': deviation_pct_at_p50
            })
            
        return results
