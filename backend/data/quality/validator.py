import pandas as pd
from typing import Tuple, List, Dict, Optional

def validate_weather_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Validate weather data and apply quality checks.
    """
    cleaned_df = df.copy()
    quality_flags = []
    
    if cleaned_df.empty:
        return cleaned_df, quality_flags

    # Ensure timestamp or time context for flags if available
    # Just getting block_no from a column if it exists, otherwise None
    
    # Rule 1: Missing values
    for col in cleaned_df.columns:
        missing_count = cleaned_df[col].isna().sum()
        total_count = len(cleaned_df)
        
        if missing_count > 0:
            missing_ratio = missing_count / total_count
            if missing_ratio < 0.1:
                cleaned_df[col] = cleaned_df[col].ffill()
            else:
                quality_flags.append({
                    'column': col,
                    'issue': 'high_missing',
                    'block_no': None, # Global issue for this batch
                    'severity': 'warning'
                })
                cleaned_df[col] = cleaned_df[col].ffill() # Still ffill to have valid data
                
    # Rule 2: Negative radiation
    solar_cols = ['shortwave_radiation', 'direct_normal_irradiance', 'diffuse_radiation', 'global_tilted_irradiance', 'ALLSKY_SFC_SW_DWN', 'ALLSKY_SFC_SW_DNI', 'ALLSKY_SFC_SW_DIFF']
    for col in solar_cols:
        if col in cleaned_df.columns:
            neg_mask = cleaned_df[col] < 0
            if neg_mask.any():
                cleaned_df.loc[neg_mask, col] = 0.0
                quality_flags.append({
                    'column': col,
                    'issue': 'negative_radiation',
                    'block_no': None,
                    'severity': 'info'
                })
                
    # Rule 3: Temperature bounds
    temp_cols = ['temperature_2m', 'T2M']
    for col in temp_cols:
        if col in cleaned_df.columns:
            outlier_mask = (cleaned_df[col] < -50) | (cleaned_df[col] > 60)
            if outlier_mask.any():
                quality_flags.append({
                    'column': col,
                    'issue': 'temp_outlier',
                    'block_no': None,
                    'severity': 'warning'
                })

    # Rule 4: Wind speed bounds
    wind_cols = ['wind_speed_10m', 'wind_speed_80m', 'wind_speed_120m', 'WS10M', 'WS50M']
    for col in wind_cols:
        if col in cleaned_df.columns:
            outlier_mask = cleaned_df[col] > 50
            if outlier_mask.any():
                cleaned_df.loc[outlier_mask, col] = 50.0
                quality_flags.append({
                    'column': col,
                    'issue': 'wind_outlier',
                    'block_no': None,
                    'severity': 'warning'
                })
                
    # Rule 5: Humidity bounds
    humidity_cols = ['relative_humidity_2m', 'RH2M']
    for col in humidity_cols:
        if col in cleaned_df.columns:
            cleaned_df[col] = cleaned_df[col].clip(0, 100)

    return cleaned_df, quality_flags

def check_avc_exceedance(generation_mw: float, avc_mw: float) -> Optional[Dict]:
    """
    Check if generation exceeds Available Capacity (AVC).
    """
    if generation_mw > avc_mw:
        return {
            'issue': 'avc_exceeded',
            'generation_mw': generation_mw,
            'avc_mw': avc_mw,
            'severity': 'info'
        }
    return None

def zero_fill_nighttime_solar(df: pd.DataFrame, ghi_col: str = 'shortwave_radiation') -> pd.DataFrame:
    """
    Set all solar radiation columns to 0.0 when GHI is 0 or less.
    """
    df_out = df.copy()
    
    if ghi_col not in df_out.columns:
        return df_out
        
    night_mask = df_out[ghi_col] <= 0
    solar_cols = [col for col in df_out.columns if 'radiation' in col.lower() or 'irradiance' in col.lower() or 'sw' in col.lower()]
    
    for col in solar_cols:
        df_out.loc[night_mask, col] = 0.0
        
    return df_out
