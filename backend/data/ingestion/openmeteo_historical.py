import httpx
import pandas as pd
import logging

logger = logging.getLogger('renewable_platform')

OPENMETEO_HISTORICAL_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = [
    "shortwave_radiation",
    "direct_normal_irradiance",
    "diffuse_radiation",
    "global_tilted_irradiance",
    "wind_speed_10m",
    "wind_speed_80m",
    "wind_speed_120m",
    "wind_direction_10m",
    "temperature_2m",
    "relative_humidity_2m",
    "cloud_cover",
]

async def fetch_historical_forecast(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch historical forecast data (previous runs) from Open-Meteo.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(HOURLY_VARIABLES)
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(OPENMETEO_HISTORICAL_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "hourly" not in data:
                logger.error(f"No hourly data in response for lat={lat}, lon={lon}")
                return pd.DataFrame()
            
            hourly_data = data["hourly"]
            df = pd.DataFrame(hourly_data)
            df['timestamp'] = pd.to_datetime(df['time'])
            df.drop(columns=['time'], inplace=True)
            return df
            
    except httpx.HTTPError as e:
        logger.error(f"HTTP error occurred while fetching historical forecast: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Unexpected error fetching historical forecast: {e}")
        return pd.DataFrame()
