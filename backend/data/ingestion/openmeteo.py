import httpx
import pandas as pd
import logging

logger = logging.getLogger('renewable_platform')

OPENMETEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"

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

async def fetch_weather_forecast(lat: float, lon: float, forecast_days: int = 3) -> pd.DataFrame:
    """
    Fetch weather forecast from Open-Meteo API.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARIABLES),
        "forecast_days": forecast_days,
        "timezone": "UTC"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(OPENMETEO_BASE_URL, params=params)
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
        logger.error(f"HTTP error occurred while fetching forecast for lat={lat}, lon={lon}: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Unexpected error fetching forecast for lat={lat}, lon={lon}: {e}")
        return pd.DataFrame()

async def fetch_all_plants_weather(plants: list[dict], forecast_days: int = 3) -> dict[str, pd.DataFrame]:
    """
    Fetch weather forecasts for multiple plants.
    """
    results = {}
    for plant in plants:
        plant_id = plant.get('id')
        lat = plant.get('lat')
        lon = plant.get('lon')
        
        if not all([plant_id, lat, lon]):
            logger.warning(f"Invalid plant config: {plant}")
            continue
            
        logger.info(f"Fetching forecast for plant {plant_id}")
        df = await fetch_weather_forecast(lat, lon, forecast_days)
        results[str(plant_id)] = df
        
    return results
