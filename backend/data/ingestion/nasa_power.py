import httpx
import pandas as pd
import logging
from typing import Optional, List

logger = logging.getLogger('renewable_platform')

NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
DEFAULT_PARAMETERS = [
    'ALLSKY_SFC_SW_DWN', 'ALLSKY_SFC_SW_DNI', 'ALLSKY_SFC_SW_DIFF', 
    'T2M', 'WS10M', 'WS50M', 'RH2M'
]

async def fetch_nasa_power(lat: float, lon: float, start_date: str, end_date: str, parameters: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Fetch historical solar irradiance data from NASA POWER API.
    """
    if parameters is None:
        parameters = DEFAULT_PARAMETERS
        
    params = {
        "parameters": ",".join(parameters),
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": start_date,
        "end": end_date,
        "format": "JSON"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(NASA_POWER_BASE_URL, params=params, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            
            properties = data.get('properties', {}).get('parameter', {})
            if not properties:
                logger.error(f"No parameter data found in NASA POWER response for lat={lat}, lon={lon}")
                return pd.DataFrame()
            
            df = pd.DataFrame(properties)
            
            # The index is the timestamp string YYYYMMDDHH, convert it to actual timestamp
            df.index = pd.to_datetime(df.index, format='%Y%m%d%H')
            df.index.name = 'timestamp'
            
            # Replace -999.0 with NaN
            df = df.replace(-999.0, pd.NA)
            
            return df
            
    except httpx.HTTPError as e:
        logger.error(f"HTTP error occurred while fetching NASA POWER data: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Unexpected error fetching NASA POWER data: {e}")
        return pd.DataFrame()
