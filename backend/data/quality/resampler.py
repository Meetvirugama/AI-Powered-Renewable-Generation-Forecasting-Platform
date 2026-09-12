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

IST_OFFSET = timedelta(hours=5, minutes=30)


def add_block_numbers(df: pd.DataFrame, time_col: str = 'timestamp') -> pd.DataFrame:
    """
    Add a block number column (1-96) and an IST time string column.

    Blocks are defined in IST, not UTC. CERC settles generation in 96 blocks of
    15 minutes where block 1 is 00:00-00:15 **IST**, so the block number must be
    derived from the IST wall clock.

    This previously used the UTC hour directly, which offset every block by
    5h30m -- 22 blocks. Open-Meteo returns UTC, so weather sampled at 00:00 UTC
    (05:30 IST, sunrise) was being labelled block 1 (midnight IST). The function
    already computed an `ist_time` column from the same shift, which is what
    made the inconsistency visible: it printed 05:30 next to block_no 1.

    It matters beyond labelling: backend.modules.forecast.feature_builder builds
    its blocks in IST, so a UTC-numbered weather frame would hand the model
    dawn irradiance as midnight and darkness as midday.
    """
    if time_col not in df.columns:
        return df

    df_out = df.copy()

    ist_time = df_out[time_col] + IST_OFFSET
    df_out['block_no'] = ist_time.dt.hour * 4 + (ist_time.dt.minute // 15) + 1
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
