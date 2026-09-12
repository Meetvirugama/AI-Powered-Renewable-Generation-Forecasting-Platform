import httpx
import pandas as pd
import logging

logger = logging.getLogger('renewable_platform')

OPENMETEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Every weather variable the forecast models were trained on, plus the hub-height
# winds the DSM side uses. Keep this a superset of
# backend.modules.forecast.feature_builder.WEATHER_FEATURES: a variable missing
# here does not fail, it arrives as NaN, and the boosters quietly fall back on a
# learned default. Seven of these (dew point, the three cloud layers, direct
# radiation, surface pressure, precipitation) were absent until the models were
# retrained, so every production frame was built with 5 fewer inputs than the
# models expect.
HOURLY_VARIABLES = [
    "shortwave_radiation",
    "direct_radiation",
    "direct_normal_irradiance",
    "diffuse_radiation",
    "global_tilted_irradiance",
    "wind_speed_10m",
    "wind_speed_80m",
    "wind_speed_120m",
    "wind_direction_10m",
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "surface_pressure",
    "precipitation",
]

async def fetch_weather_forecast(
    lat: float, lon: float, forecast_days: int = 3, past_days: int = 1
) -> pd.DataFrame:
    """Fetch weather forecast from Open-Meteo API.

    `past_days` defaults to 1 and is not really optional. A settlement day runs
    00:00-23:45 IST, so its first 22 blocks fall on the *previous* UTC day, from
    18:30Z onward. Open-Meteo's forecast window opens at 00:00 UTC today, so a
    request for today returned nothing for those blocks.

    That failed quietly rather than loudly: 22 of 96 blocks arrived with no
    weather, the frame sat at 80.7% populated -- above the engine's 75% floor --
    and 00:00-05:30 IST was predicted from clock features alone. The visible
    symptom was a solar plant showing a non-zero P90 at midnight, because the
    night-time clamp keys on measured irradiance and there was none to read.

    A day-ahead request never hit this, which is why it survived testing:
    tomorrow's 00:00 IST is today's 18:30Z, comfortably inside the window. Only
    a request for *today* is affected -- which is what every dashboard load does
    by default.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARIABLES),
        "forecast_days": forecast_days,
        "past_days": past_days,
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
