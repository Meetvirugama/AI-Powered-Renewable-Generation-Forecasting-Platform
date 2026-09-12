import pandas as pd
from datetime import timedelta

def resample_hourly_to_15min(df: pd.DataFrame, time_col: str = 'timestamp') -> pd.DataFrame:
    """
    Resample hourly weather data to 15-minute frequency using linear interpolation.
    """
    if time_col not in df.columns:
        return df
        
    # Make a copy and set the index
    resampled_df = df.copy()
    resampled_df.set_index(time_col, inplace=True)
    
    # Resample and interpolate numeric columns
    numeric_cols = resampled_df.select_dtypes(include=['number']).columns
    resampled_df = resampled_df[numeric_cols].resample('15min').interpolate(method='linear')
    
    # Reset index to bring time_col back as a column
    resampled_df.reset_index(inplace=True)
    return resampled_df

def add_block_numbers(df: pd.DataFrame, time_col: str = 'timestamp') -> pd.DataFrame:
    """
    Add a block number column (1-96) and an IST time string column.
    """
    if time_col not in df.columns:
        return df
        
    df_out = df.copy()
    
    # Calculate block number: hour * 4 + minute / 15 + 1
    df_out['block_no'] = df_out[time_col].dt.hour * 4 + (df_out[time_col].dt.minute // 15) + 1
    
    # Add IST time column
    ist_time = df_out[time_col] + timedelta(hours=5, minutes=30)
    df_out['ist_time'] = ist_time.dt.strftime('%H:%M')
    
    return df_out

def add_ist_columns(df: pd.DataFrame, utc_col: str = 'timestamp') -> pd.DataFrame:
    """
    Add a timestamp_ist column converting UTC to IST.
    """
    if utc_col not in df.columns:
        return df
        
    df_out = df.copy()
    df_out['timestamp_ist'] = df_out[utc_col] + timedelta(hours=5, minutes=30)
    return df_out
