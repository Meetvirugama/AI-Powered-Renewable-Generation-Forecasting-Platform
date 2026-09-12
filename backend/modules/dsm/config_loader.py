from datetime import date
import yaml
from pathlib import Path

class DSMRuleConfig:
    """Loader and configuration holder for DSM rules."""
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

    def get_params_for_date(self, target_date: date) -> dict:
        """Returns {x, solar_band, wind_band} for the given date by finding the latest x_trajectory entry that's <= target_date."""
        trajectories = self._config.get('x_trajectory', [])
        best_match = None
        best_date = date.min
        
        for entry in trajectories:
            entry_date_str = entry.get('date') or entry.get('from')
            try:
                entry_date = date.fromisoformat(entry_date_str)
                if entry_date <= target_date and entry_date >= best_date:
                    best_match = entry
                    best_date = entry_date
            except (ValueError, TypeError):
                continue
                
        x_val = best_match.get('x', 1.0) if best_match else self._config.get('default_x', 1.0)
        solar_band = best_match.get('solar_band', 0.10) if best_match else self._config.get('bands', {}).get('solar_band', 0.10)
        wind_band = best_match.get('wind_band', 0.15) if best_match else self._config.get('bands', {}).get('wind_band', 0.15)
        
        return {
            'x': float(x_val),
            'solar_band': float(solar_band),
            'wind_band': float(wind_band)
        }

    def get_params_for_year(self, rule_year: int) -> dict:
        """Convenience: given a year like 2026, returns params for April 1 of that year."""
        target_date = date(rule_year, 4, 1)
        return self.get_params_for_date(target_date)

    def get_frequency_multiplier(self, freq_hz: float, is_over_injection: bool) -> float:
        """Returns the multiplier based on frequency band. For over-injection at freq >= 50.05, returns 0.0 (zero payment)."""
        if is_over_injection and freq_hz >= 50.05:
            return 0.0
            
        multipliers = self._config.get('frequency_multipliers', [])
        for entry in multipliers:
            min_f = float(entry.get('min', entry.get('freq_gte', -float('inf'))))
            max_f = float(entry.get('max', entry.get('freq_lt', entry.get('freq_lte', float('inf')))))
            
            if min_f <= freq_hz < max_f or (max_f == float('inf') and freq_hz >= min_f):
                if is_over_injection:
                    return float(entry.get('over', 1.0))
                else:
                    return float(entry.get('under', 1.0))
                    
        # Fallback standard CERC 2024/2026 multipliers
        if freq_hz < 49.90:
            return 2.0
        elif 49.90 <= freq_hz < 49.95:
            return 1.5
        elif 49.95 <= freq_hz <= 50.03:
            return 1.0
        elif 50.03 < freq_hz < 50.05:
            return 0.75
        elif freq_hz >= 50.05:
            return 0.0 if is_over_injection else 1.0
        return 1.0

    @property
    def rule_version(self) -> str:
        """Returns the rule_version string from YAML."""
        return str(self._config.get('rule_version', 'CERC_DSM_2026'))

    @property
    def ncd_default(self) -> float:
        """Returns the default NCD value from YAML."""
        return float(self._config.get('ncd_default_inr_per_mwh', self._config.get('ncd_default', 450.0)))

    @property
    def is_seller_side(self) -> bool:
        """Returns is_seller_side boolean from YAML."""
        return bool(self._config.get('seller_side', self._config.get('is_seller_side', True)))
