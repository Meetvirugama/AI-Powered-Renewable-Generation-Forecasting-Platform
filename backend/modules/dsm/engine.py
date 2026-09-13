from datetime import date
from .config_loader import DSMRuleConfig


def quantile_weights(levels) -> dict[float, float]:
    """Probability mass each forecast quantile stands for (midpoint rule).

    The sample at level q_i represents the interval halfway to its neighbours,
    with 0 and 1 as the outer edges, normalised to sum to 1. P50 therefore
    carries far more weight than P05, which is what makes the result a true
    expected rupee value rather than an average of seven penalties.
    """
    ordered = sorted(float(q) for q in levels)
    weights: dict[float, float] = {}
    for i, q in enumerate(ordered):
        lower = ordered[i - 1] if i > 0 else 0.0
        upper = ordered[i + 1] if i + 1 < len(ordered) else 1.0
        weights[q] = (upper - lower) / 2.0
    total = sum(weights.values()) or 1.0
    return {q: w / total for q, w in weights.items()}


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

    def compute_block_penalty(self, actual_mw: float, schedule_mw: float, avc_mw: float, freq_hz: float, ncd_inr_per_mwh: float, asset_type: str, band: float | None = None) -> float:
        """Compute penalty for a single block (in INR).

        `band` overrides the tolerance band normally chosen from `asset_type`.
        A pool mixing solar and wind has no single technology, so pooling passes
        a capacity-weighted band here rather than labelling the pool as one type.
        """
        dev_pct = self.compute_deviation_pct(actual_mw, schedule_mw, avc_mw)
        if band is None:
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

    def compute_expected_penalty(self, quantile_forecasts: dict[float, float], schedule_mw: float, avc_mw: float, freq_hz: float, ncd: float, asset_type: str, band: float | None = None) -> float:
        """Probability-weighted expected penalty across quantile forecasts.

        This used to be a plain average of the per-quantile penalties. P05 and
        P50 are not equally likely outcomes, so equal weighting roughly tripled
        the influence of the tails -- and the schedule optimiser, which weights
        by probability, disagreed with every other caller. The Actions page
        showed the same plant's penalty as ₹1,53,452 in one panel and ₹2,86,619
        in the next. Every caller now gets the same expectation.
        """
        if not quantile_forecasts:
            return 0.0
        weights = quantile_weights(quantile_forecasts.keys())
        return sum(
            weights[float(q)] * self.compute_block_penalty(actual_mw, schedule_mw, avc_mw, freq_hz, ncd, asset_type, band)
            for q, actual_mw in quantile_forecasts.items()
        )

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
