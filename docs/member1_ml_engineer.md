# Member 1 — ML Engineer
## Execution Plan: Senior Engineer Level
### AI-Powered Renewable Generation Forecasting Platform

---

> **You are the most critical person on this team.** Everything that makes this project unique — probabilistic forecasting, ₹ penalty pricing, schedule optimisation — lives in your modules. The rest of the team wraps your work in APIs, dashboards, and infrastructure.

---

## Your Stack
```
Python 3.11
pvlib                  # solar physics
lightgbm               # quantile ML model
chronos-forecasting    # Amazon Chronos-2-small
pulp + cylp (CBC)      # battery LP optimiser
scikit-learn           # calibration, metrics
pandas + numpy         # everything
openmeteo-requests     # weather data
PyYAML                 # DSM rule config
shap                   # feature attribution
matplotlib + plotly    # evaluation charts
mlflow                 # experiment tracking
Google Colab T4 GPU    # Chronos training
```

---

## Day 1 — Environment Setup + Data Acquisition

### Step 1: Install everything in Colab
```python
# Colab cell 1 - paste this at the top of every notebook
!pip install -q pvlib lightgbm chronos-forecasting[torch] \
    openmeteo-requests requests-cache retry-requests \
    scikit-learn shap pulp cylp PyYAML mlflow \
    plotly kaleido rank-bm25

import pandas as pd
import numpy as np
import pvlib
import lightgbm as lgb
from chronos import ChronosPipeline
import torch
import pulp
import yaml
import shap
import mlflow
import warnings
warnings.filterwarnings('ignore')

# Set random seeds for reproducibility
np.random.seed(42)
torch.manual_seed(42)
```

### Step 2: NASA POWER India Solar Benchmark Pull (Notebook 01)

```python
# 4.38 million hourly rows, 50 Indian cities, 2016–2025
# CC BY 4.0 — free, no API key

import requests

# 10 key cities for training (cover Gujarat + diverse climates)
CITIES = {
    "Gandhinagar":  {"lat": 23.2156, "lon": 72.6369},
    "Rajkot":       {"lat": 22.3039, "lon": 70.8022},
    "Kutch":        {"lat": 23.7337, "lon": 69.8597},
    "Palanpur":     {"lat": 24.1741, "lon": 72.4330},
    "Jaisalmer":    {"lat": 26.9157, "lon": 70.9083},  # high solar
    "Jodhpur":      {"lat": 26.2389, "lon": 73.0243},
    "Jaipur":       {"lat": 26.9124, "lon": 75.7873},
    "Nagpur":       {"lat": 21.1458, "lon": 79.0882},
    "Hyderabad":    {"lat": 17.3850, "lon": 78.4867},
    "Chennai":      {"lat": 13.0827, "lon": 80.2707},
}

def fetch_nasa_power(lat, lon, start="2016", end="2025"):
    """
    Fetches hourly solar irradiance + met data from NASA POWER API.
    Returns DataFrame with columns: GHI, DNI, DHI, T2M, WS10M, RH2M
    """
    url = "https://power.larc.nasa.gov/api/temporal/hourly/point"
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI,ALLSKY_SFC_SW_DIFF,T2M,WS10M,RH2M",
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": f"{start}0101",
        "end": f"{end}1231",
        "format": "JSON",
        "time-standard": "UTC",
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()["properties"]["parameter"]

    df = pd.DataFrame(data)
    df.index = pd.to_datetime(df.index, format="%Y%m%d%H")
    df.index.name = "timestamp_utc"
    df.columns = ["GHI", "DNI", "DHI", "T2M_C", "WS10M_ms", "RH2M_pct"]

    # NASA POWER uses -999 for missing — replace with NaN
    df = df.replace(-999, np.nan)
    # Drop ALLSKY_KT (leaks future info) — do NOT include this feature
    return df

# Pull all cities and save
all_city_dfs = {}
for city, coords in CITIES.items():
    print(f"Fetching {city}...")
    df = fetch_nasa_power(coords["lat"], coords["lon"])
    all_city_dfs[city] = df
    df.to_parquet(f"data_{city.lower()}.parquet")

print("Done. Total rows:", sum(len(v) for v in all_city_dfs.values()))
```

### Step 3: Open-Meteo Historical Forecast Pull (as-issued weather)

```python
import openmeteo_requests
import requests_cache
from retry_requests import retry

# Set up cached session
cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
om = openmeteo_requests.Client(session=retry_session)

def fetch_openmeteo_historical_forecast(lat, lon,
                                         start_date="2024-01-01",
                                         end_date="2024-12-31",
                                         model="best_match"):
    """
    Open-Meteo Previous Runs API — returns weather AS IT WAS ISSUED,
    not the ERA5 reanalysis. Critical for realistic training data.
    Lead time = 24h forecast (matches our day-ahead use case).
    """
    url = "https://previous-runs-api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
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
            "precipitation",
        ],
        "wind_speed_unit": "ms",
        "start_date": start_date,
        "end_date": end_date,
        "models": model,
        "past_days": 92,  # max look-back
    }
    responses = om.weather_api(url, params=params)
    response = responses[0]
    hourly = response.Hourly()

    times = pd.date_range(
        start=pd.Timestamp(hourly.Time(), unit="s", tz="UTC"),
        end=pd.Timestamp(hourly.TimeEnd(), unit="s", tz="UTC"),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left",
    )
    cols = ["GHI", "DNI", "DHI", "GTI", "WS10m", "WS80m", "WS120m",
            "WD10m", "T2m", "RH2m", "cloud_cover", "precip"]
    df = pd.DataFrame({
        col: hourly.Variables(i).ValuesAsNumpy()
        for i, col in enumerate(cols)
    }, index=times)
    df.index.name = "timestamp_utc"
    return df

# Pull for Gujarat plant locations
for plant_id, coords in {
    "GJ_SOLAR_A": (23.2156, 72.6369),
    "GJ_SOLAR_B": (22.3039, 70.8022),
    "GJ_WIND_C":  (23.6102, 68.9761),
    "GJ_SOLAR_D": (24.1858, 72.4337),
}.items():
    df = fetch_openmeteo_historical_forecast(coords[0], coords[1])
    df.to_parquet(f"weather_forecast_{plant_id}.parquet")
    print(f"{plant_id}: {len(df)} hourly rows")
```

---

## Day 2 — Preprocessing (Notebook 02)

```python
def preprocess_weather(df_hourly: pd.DataFrame,
                       plant_tz="Asia/Kolkata") -> pd.DataFrame:
    """
    Convert hourly weather forecast to 15-min blocks.
    This is the KEY step that makes our data compatible with DSM blocks.
    """
    # 1. Resample to 15-min via linear interpolation
    df_15min = df_hourly.resample("15min").interpolate(method="linear")

    # 2. Add IST timestamp for display (store UTC internally)
    df_15min["timestamp_ist"] = df_15min.index.tz_convert(plant_tz)

    # 3. Add block number (1–96 per day)
    df_15min["block_no"] = (
        (df_15min.index.hour * 4) + (df_15min.index.minute // 15) + 1
    )

    # 4. Clip physically impossible values
    df_15min["GHI"] = df_15min["GHI"].clip(lower=0, upper=1400)
    df_15min["DNI"] = df_15min["DNI"].clip(lower=0, upper=1200)
    df_15min["DHI"] = df_15min["DHI"].clip(lower=0, upper=800)
    df_15min["WS10m"] = df_15min["WS10m"].clip(lower=0, upper=60)

    # 5. Flag nighttime (solar elevation < -5°) — do NOT remove
    # (Chronos needs to see the zeros)
    df_15min["is_night"] = df_15min["GHI"] < 1.0

    # 6. Forward-fill small gaps (< 4 consecutive = 1 hour)
    df_15min = df_15min.fillna(method="ffill", limit=4)

    # 7. Flag rows still NaN after fill
    df_15min["data_quality_flag"] = df_15min.isnull().any(axis=1)

    return df_15min


def check_leakage(df: pd.DataFrame, target_col: str,
                   feature_cols: list, forecast_horizon_blocks: int):
    """
    CRITICAL: Ensure no feature uses data from after the forecast cutoff.
    Call this before training. Will raise ValueError if leakage detected.
    """
    lag_cols = [c for c in feature_cols if "lag" in c.lower()]
    for col in lag_cols:
        # Extract lag number from column name like "gen_lag_96"
        lag = int(col.split("_")[-1])
        if lag < forecast_horizon_blocks:
            raise ValueError(
                f"LEAKAGE DETECTED: Feature '{col}' uses lag={lag} blocks "
                f"but forecast horizon is {forecast_horizon_blocks} blocks. "
                f"Minimum lag must be >= {forecast_horizon_blocks}."
            )
    print("✅ No leakage detected. All lags >= forecast horizon.")
```

---

## Day 3 — Physics Simulation (Notebook 03)

This is the core of our "physics-informed" approach. Write this as `backend/modules/forecast/physics.py`.

```python
# backend/modules/forecast/physics.py
import pvlib
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

class SolarPhysicsModel:
    """
    Physics-based solar generation estimator using pvlib.
    Converts weather forecast into expected DC/AC generation.
    Output is used as a FEATURE for LightGBM, not as the final forecast.
    """

    def __init__(self, lat: float, lon: float, altitude_m: float,
                 tilt_deg: float, azimuth_deg: float,
                 avc_mw: float, efficiency: float = 0.18,
                 temp_coeff: float = -0.004):
        self.lat = lat
        self.lon = lon
        self.altitude = altitude_m
        self.tilt = tilt_deg
        self.azimuth = azimuth_deg
        self.avc_mw = avc_mw
        self.efficiency = efficiency       # panel efficiency (fraction)
        self.temp_coeff = temp_coeff       # power loss per °C above STC (25°C)
        self.location = pvlib.location.Location(lat, lon, altitude=altitude_m,
                                                 tz="UTC")

    def compute_solar_position(self, timestamps: pd.DatetimeIndex) -> pd.DataFrame:
        return self.location.get_solarposition(timestamps)

    def compute_clear_sky(self, timestamps: pd.DatetimeIndex) -> pd.DataFrame:
        """Ineichen clear-sky model — gives theoretical max GHI."""
        return self.location.get_clearsky(timestamps, model="ineichen")

    def compute_poa_irradiance(self, timestamps, ghi, dhi, dni) -> pd.Series:
        """
        Compute Plane-of-Array (POA) irradiance from GHI/DNI/DHI.
        POA is what actually hits the panel at its tilt/azimuth angle.
        """
        solar_pos = self.compute_solar_position(timestamps)

        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt=self.tilt,
            surface_azimuth=self.azimuth,
            dni=dni,
            ghi=ghi,
            dhi=dhi,
            solar_zenith=solar_pos["apparent_zenith"],
            solar_azimuth=solar_pos["azimuth"],
            model="haydavies",
        )
        return poa["poa_global"].clip(lower=0)

    def compute_cell_temperature(self, poa_irradiance, ambient_temp_c,
                                  wind_speed_ms) -> pd.Series:
        """
        Faiman model: T_cell = T_amb + POA / (U0 + U1 * wind_speed)
        U0 = 25 W/(m²·K), U1 = 6.84 W·s/(m³·K) — standard NOCT coefficients
        """
        U0, U1 = 25.0, 6.84
        return ambient_temp_c + poa_irradiance / (U0 + U1 * wind_speed_ms)

    def compute_expected_generation(self, timestamps, ghi, dhi, dni,
                                     ambient_temp_c, wind_speed_ms) -> pd.Series:
        """
        Full physics chain: POA → cell temperature → DC power → AC power.
        Returns: expected_generation_mw (clipped at AvC)
        """
        poa = self.compute_poa_irradiance(timestamps, ghi, dhi, dni)
        t_cell = self.compute_cell_temperature(poa, ambient_temp_c, wind_speed_ms)

        # Standard Test Condition (STC): 1000 W/m², 25°C
        stc_irradiance = 1000.0
        dc_power_fraction = (poa / stc_irradiance) * (
            1 + self.temp_coeff * (t_cell - 25)
        )
        dc_power_fraction = dc_power_fraction.clip(lower=0, upper=1.2)

        # AC power (simplified: no inverter curve, just efficiency)
        ac_power_mw = dc_power_fraction * self.efficiency * self.avc_mw
        ac_power_mw = ac_power_mw.clip(lower=0, upper=self.avc_mw)

        # Add clear-sky index as a feature column
        cs = self.compute_clear_sky(timestamps)
        cs_ghi = cs["ghi"].replace(0, np.nan)
        clear_sky_index = (ghi / cs_ghi).fillna(0).clip(0, 2)

        return pd.DataFrame({
            "expected_gen_mw": ac_power_mw,
            "poa_irradiance": poa,
            "cell_temp_c": t_cell,
            "clear_sky_index": clear_sky_index,
            "clear_sky_ghi": cs["ghi"],
        }, index=timestamps)


class WindPhysicsModel:
    """
    Wind generation model using a fitted sigmoid power curve.
    Power curve fitted on CARE Wind Farm A data (CC BY-SA 4.0).
    """

    def __init__(self, avc_mw: float, hub_height_m: float = 120.0,
                  roughness_length: float = 0.03):
        self.avc_mw = avc_mw
        self.hub_height = hub_height_m
        self.z0 = roughness_length
        self.power_curve_params = None  # set by fit_power_curve()

    def extrapolate_wind_speed(self, ws_10m, ws_80m=None,
                                ws_120m=None) -> pd.Series:
        """
        Extrapolate wind speed to hub height using log law.
        If 80m or 120m data available, use them directly.
        """
        if ws_120m is not None and self.hub_height <= 120:
            return ws_120m  # already close enough
        elif ws_80m is not None:
            # Log law between 80m and hub height
            ratio = np.log(self.hub_height / self.z0) / np.log(80 / self.z0)
            return ws_80m * ratio
        else:
            # Log law from 10m
            ratio = np.log(self.hub_height / self.z0) / np.log(10 / self.z0)
            return ws_10m * ratio

    @staticmethod
    def _sigmoid_power_curve(ws, k, ws50, p_rated):
        """
        Smooth sigmoid approximation of a turbine power curve.
        k: steepness, ws50: wind speed at 50% rated, p_rated: rated power
        """
        return p_rated / (1 + np.exp(-k * (ws - ws50)))

    def fit_power_curve(self, care_df: pd.DataFrame):
        """
        Fit sigmoid on CARE Wind Farm A data.
        care_df columns: wind_speed_ms, power_mw
        """
        # Remove cut-in/cut-out edge cases
        df = care_df[(care_df.wind_speed_ms > 1) &
                     (care_df.wind_speed_ms < 25)].copy()
        df = df.dropna()

        params, _ = curve_fit(
            self._sigmoid_power_curve,
            df.wind_speed_ms,
            df.power_mw,
            p0=[1.0, 8.0, self.avc_mw],
            bounds=([0.1, 3.0, 0.1], [5.0, 15.0, self.avc_mw * 1.1]),
            maxfev=10000,
        )
        self.power_curve_params = params
        print(f"Power curve fitted: k={params[0]:.3f}, "
              f"ws50={params[1]:.2f} m/s, p_rated={params[2]:.2f} MW")

    def predict_power(self, wind_speed_hub: pd.Series) -> pd.Series:
        if self.power_curve_params is None:
            raise ValueError("Call fit_power_curve() first.")
        k, ws50, p_rated = self.power_curve_params
        power = self._sigmoid_power_curve(wind_speed_hub, k, ws50, p_rated)
        return pd.Series(power, index=wind_speed_hub.index).clip(0, self.avc_mw)
```

---

## Day 4 — Feature Engineering (Notebook 04)

```python
# backend/modules/forecast/features.py

import pvlib
import numpy as np
import pandas as pd

INDIAN_SEASONS = {
    12: "winter", 1: "winter", 2: "winter",
    3: "summer", 4: "summer", 5: "summer",
    6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon",
    10: "post_monsoon", 11: "post_monsoon",
}

def build_feature_matrix(weather_15min: pd.DataFrame,
                           physics_output: pd.DataFrame,
                           generation_history: pd.DataFrame,
                           plant_metadata: dict,
                           forecast_horizon_blocks: int = 96) -> pd.DataFrame:
    """
    Builds the complete ML feature matrix for a plant.
    MUST be called with forecast_horizon_blocks to enforce lag safety.

    Args:
        weather_15min: preprocessed weather at 15-min resolution
        physics_output: SolarPhysicsModel or WindPhysicsModel output
        generation_history: historical actual generation (MW) at 15-min
        plant_metadata: dict with avc_mw, type, lat, lon, pool_id
        forecast_horizon_blocks: minimum safe lag (96 for day-ahead)
    """
    df = weather_15min.copy()

    # === Weather features ===
    df["ghi"] = df["GHI"]
    df["dni"] = df["DNI"]
    df["dhi"] = df["DHI"]
    df["wind_10m"] = df["WS10m"]
    df["wind_80m"] = df.get("WS80m", df["WS10m"] * 1.3)
    df["temp_c"] = df["T2m"]
    df["humidity_pct"] = df["RH2m"]
    df["cloud_cover_pct"] = df.get("cloud_cover", 0.0)

    # === Physics features ===
    df["expected_gen_mw"] = physics_output["expected_gen_mw"]
    df["poa_irradiance"] = physics_output["poa_irradiance"]
    df["cell_temp_c"] = physics_output["cell_temp_c"]
    df["clear_sky_index"] = physics_output["clear_sky_index"]
    df["clear_sky_ghi"] = physics_output["clear_sky_ghi"]

    # === Solar geometry features (pvlib) ===
    location = pvlib.location.Location(
        plant_metadata["lat"], plant_metadata["lon"], tz="UTC"
    )
    sol_pos = location.get_solarposition(df.index)
    df["solar_zenith"] = sol_pos["apparent_zenith"]
    df["solar_azimuth"] = sol_pos["azimuth"]
    df["solar_elevation"] = 90 - sol_pos["apparent_zenith"]
    df["cos_zenith"] = np.cos(np.radians(sol_pos["apparent_zenith"])).clip(0)

    # === Time features ===
    df["hour"] = df.index.hour
    df["minute"] = df.index.minute
    df["block_no"] = df.index.hour * 4 + df.index.minute // 15 + 1
    df["day_of_year"] = df.index.day_of_year
    df["month"] = df.index.month
    df["day_of_week"] = df.index.day_of_week
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["season"] = df["month"].map(INDIAN_SEASONS)
    df = pd.get_dummies(df, columns=["season"], drop_first=True)

    # Cyclical encoding for time (better than raw integers for ML)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["doy_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365)
    df["doy_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365)

    # === Generation lag features (SAFE — >= forecast horizon) ===
    gen = generation_history["generation_mw"].reindex(df.index)

    # 24h lag (96 blocks) — earliest safe lag for day-ahead forecast
    df["gen_lag_96"] = gen.shift(forecast_horizon_blocks)
    # 48h lag
    df["gen_lag_192"] = gen.shift(forecast_horizon_blocks * 2)
    # 1-week same block
    df["gen_lag_672"] = gen.shift(forecast_horizon_blocks * 7)

    # Rolling statistics (safe: computed on t-96 and before)
    gen_safe = gen.shift(forecast_horizon_blocks)
    df["gen_roll_mean_96"] = gen_safe.rolling(96).mean()   # 24h mean
    df["gen_roll_std_96"] = gen_safe.rolling(96).std()
    df["gen_roll_max_96"] = gen_safe.rolling(96).max()

    # === Site metadata features ===
    df["avc_mw"] = plant_metadata["avc_mw"]
    df["is_solar"] = int(plant_metadata["type"] == "solar")
    df["is_wind"] = int(plant_metadata["type"] == "wind")
    df["lat"] = plant_metadata["lat"]
    df["lon"] = plant_metadata["lon"]

    # === Target ===
    df["target_gen_mw"] = gen  # actual generation (only for training)

    # Drop rows with NaN in critical features
    feature_cols = [c for c in df.columns if c not in
                    ["target_gen_mw", "timestamp_ist", "data_quality_flag"]]
    df = df.dropna(subset=["gen_lag_96"])  # need at least 24h of history

    return df, feature_cols
```

---

## Day 5 — LightGBM Quantile Model (Notebook 05)

```python
# backend/modules/forecast/lgbm_model.py

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.isotonic import IsotonicRegression
import pickle
import mlflow

QUANTILE_LEVELS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40,
                   0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
                   0.85, 0.90, 0.95]

BASE_PARAMS = {
    "boosting_type": "gbdt",
    "n_estimators": 1000,
    "learning_rate": 0.03,
    "num_leaves": 63,
    "min_child_samples": 20,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "verbose": -1,
    "n_jobs": -1,
    "random_state": 42,
}

class LGBMQuantileForecaster:
    """
    LightGBM quantile regression model.
    Trains one model per quantile, then sorts predictions to prevent crossing.
    """

    def __init__(self, quantile_levels=None):
        self.quantile_levels = quantile_levels or QUANTILE_LEVELS
        self.models = {}           # {q: lgb.Booster}
        self.calibrators = {}      # {q: IsotonicRegression}
        self.feature_names = None

    def train(self, X_train: pd.DataFrame, y_train: pd.Series,
               X_val: pd.DataFrame, y_val: pd.Series,
               plant_id: str = "plant"):

        mlflow.start_run(run_name=f"lgbm_{plant_id}")
        mlflow.log_params(BASE_PARAMS)

        self.feature_names = X_train.columns.tolist()

        for q in self.quantile_levels:
            print(f"Training quantile q={q:.2f}...")
            params = {**BASE_PARAMS, "objective": "quantile", "alpha": q}
            model = lgb.train(
                params,
                lgb.Dataset(X_train, label=y_train),
                valid_sets=[lgb.Dataset(X_val, label=y_val)],
                num_boost_round=1000,
                callbacks=[
                    lgb.early_stopping(50, verbose=False),
                    lgb.log_evaluation(100),
                ],
            )
            self.models[q] = model
            val_pred = model.predict(X_val)
            pinball = self._pinball_loss(y_val, val_pred, q)
            mlflow.log_metric(f"pinball_q{int(q*100):02d}", pinball)
            print(f"  q={q:.2f} val pinball: {pinball:.4f}")

        mlflow.end_run()

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Returns DataFrame with columns P05, P10, ..., P95.
        Applies isotonic regression sort to prevent quantile crossing.
        """
        raw_preds = np.column_stack([
            self.models[q].predict(X)
            for q in self.quantile_levels
        ])

        # Sort each row (prevent crossing) using isotonic regression
        sorted_preds = np.apply_along_axis(
            lambda row: np.sort(row), axis=1, arr=raw_preds
        )

        cols = [f"P{int(q*100):02d}" for q in self.quantile_levels]
        result = pd.DataFrame(sorted_preds, columns=cols, index=X.index)
        # Clip to physical bounds
        result = result.clip(lower=0)
        return result

    @staticmethod
    def _pinball_loss(y_true, y_pred, q):
        err = y_true - y_pred
        return np.mean(np.where(err >= 0, q * err, (q - 1) * err))

    def compute_shap(self, X_sample: pd.DataFrame, quantile=0.50):
        """Compute SHAP values for P50 model for explainability."""
        model = self.models[quantile]
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)
        return shap_values, self.feature_names

    def calibrate(self, X_cal: pd.DataFrame, y_cal: pd.Series):
        """
        Apply isotonic regression calibration on calibration set.
        Ensures stated quantile coverage matches empirical coverage.
        """
        raw_preds = self.predict(X_cal)
        for q in self.quantile_levels:
            col = f"P{int(q*100):02d}"
            cal = IsotonicRegression(out_of_bounds="clip")
            cal.fit(raw_preds[col].values, y_cal.values)
            self.calibrators[q] = cal
        print("✅ Calibration complete.")

    def save(self, path: str):
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str):
        with open(path, "rb") as f:
            return pickle.load(f)
```

---

## Day 6 — Chronos-2 Integration (Notebook 06 & 07)

```python
# backend/modules/forecast/chronos_model.py

import torch
import numpy as np
import pandas as pd
from chronos import ChronosPipeline

class Chronos2Forecaster:
    """
    Wrapper around Amazon Chronos-2-small (28M params).
    Uses weather forecast as known future covariates.
    Best for: new plants with little history (cold start).
    """

    def __init__(self, model_id="amazon/chronos-t5-small",
                  device="cuda" if torch.cuda.is_available() else "cpu"):
        self.device = device
        print(f"Loading Chronos-2 on {device}...")
        self.pipeline = ChronosPipeline.from_pretrained(
            model_id,
            device_map=device,
            torch_dtype=torch.bfloat16,
        )
        print("✅ Chronos-2 loaded.")

    def predict(self, history_mw: pd.Series,
                 prediction_length: int = 96,
                 num_samples: int = 500,
                 quantile_levels=None) -> pd.DataFrame:
        """
        Zero-shot probabilistic forecast.
        history_mw: last 7 days of 15-min generation (672 observations min)
        prediction_length: number of 15-min blocks to forecast (96=24h)
        num_samples: Monte Carlo samples for quantile estimation
        """
        if quantile_levels is None:
            quantile_levels = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]

        context = torch.tensor(history_mw.values, dtype=torch.float32).unsqueeze(0)

        forecast = self.pipeline.predict(
            context=context,
            prediction_length=prediction_length,
            num_samples=num_samples,
            temperature=1.0,
            top_k=50,
            top_p=1.0,
        )

        # forecast shape: (1, num_samples, prediction_length)
        samples = forecast[0].numpy()  # (num_samples, prediction_length)

        # Compute quantiles from samples
        quantiles = np.quantile(samples, quantile_levels, axis=0).T
        # Shape: (prediction_length, num_quantile_levels)

        cols = [f"P{int(q*100):02d}" for q in quantile_levels]
        result = pd.DataFrame(quantiles, columns=cols)
        result = result.clip(lower=0)
        return result

# === Fine-tuning (Notebook 07) ===
# Run this in Colab with T4 GPU
# Uses chronos-forecasting training script with our plant data

"""
Fine-tuning command (run in Colab terminal):
python -m chronos.scripts.training \
  --config config/chronos_finetune_config.yaml \
  --output-dir checkpoints/chronos_finetuned/

# chronos_finetune_config.yaml:
training_data_paths:
  - data/training_timeseries.arrow   # convert pandas to Arrow format
prediction_length: 96
context_length: 672
model_id: amazon/chronos-t5-small
num_training_steps: 1000
learning_rate: 1e-4
per_device_train_batch_size: 32
"""
```

---

## Day 7 — DSM Engine (THE MOST IMPORTANT FILE)

```python
# backend/modules/dsm/engine.py

import numpy as np
import pandas as pd
import yaml
from datetime import date
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class DSMBlock:
    block_no: int
    actual_mw: float
    schedule_mw: float
    freq_hz: float
    deviation_mw: float
    deviation_pct: float
    in_tolerance: bool
    freq_multiplier: float
    penalty_inr: float

class DSMEngine:
    """
    CERC Deviation Settlement Mechanism engine for renewable generators (sellers).
    Implements CERC DSM Regulations 2024 + 2026 amendment.

    Key formula:
    Deviation% = 100 × (Actual_MW − Schedule_MW) / (X·AvC + (1−X)·Schedule_MW)

    Where X falls from 1.0 (2026) to 0.0 (2031) per the X-trajectory.

    IMPORTANT: This is the SELLER-SIDE formula (generators injecting power).
    The buyer-side (discom overdraw) formula is different — see CERC DSM 2024 Section 6.
    """

    def __init__(self, config_path: str, rule_date: Optional[date] = None):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.rule_date = rule_date or date.today()
        self.x, self.solar_band, self.wind_band = self._resolve_x_and_bands()

        print(f"DSM Engine initialised:")
        print(f"  Rule version: {self.config['rule_version']}")
        print(f"  Rule date: {self.rule_date}")
        print(f"  X (tolerance factor): {self.x:.2f}")
        print(f"  Solar tolerance band: ±{self.solar_band*100:.1f}%")
        print(f"  Wind tolerance band:  ±{self.wind_band*100:.1f}%")

    def _resolve_x_and_bands(self):
        """Find the applicable X and tolerance band for self.rule_date."""
        trajectory = self.config["x_trajectory"]
        x = trajectory[0]["x"]
        solar_band = trajectory[0]["solar_band"]
        wind_band = trajectory[0]["wind_band"]

        for entry in trajectory:
            entry_date = date.fromisoformat(entry["from"])
            if self.rule_date >= entry_date:
                x = entry["x"]
                solar_band = entry["solar_band"]
                wind_band = entry["wind_band"]

        return x, solar_band, wind_band

    def _get_freq_multiplier(self, freq_hz: float,
                              is_over_injection: bool) -> float:
        """
        Returns the frequency multiplier for penalty calculation.
        Over-injection at f >= 50.05 Hz: zero payment (curtailed, unpaid).
        """
        if is_over_injection and freq_hz >= 50.05:
            return 0.0  # ← This is the 50.05 Hz rule — no payment

        for band in self.config["frequency_multipliers"]:
            f_min = band.get("freq_gte", -np.inf)
            f_max = band.get("freq_lt", np.inf)
            if f_min <= freq_hz < f_max:
                return band.get("over" if is_over_injection else "under", 1.0)

        return 1.0  # default normal frequency

    def compute_deviation_pct(self, actual_mw: float, schedule_mw: float,
                               avc_mw: float) -> float:
        """
        THE CORE FORMULA. Read CERC DSM 2024 Section 5.1 carefully.
        Denominator = X·AvC + (1−X)·Schedule
        """
        denom = self.x * avc_mw + (1 - self.x) * schedule_mw
        if denom <= 0:
            return 0.0
        return 100.0 * (actual_mw - schedule_mw) / denom

    def compute_block_penalty(self, actual_mw: float, schedule_mw: float,
                               avc_mw: float, freq_hz: float,
                               ncd_inr_per_mwh: float,
                               asset_type: str = "solar") -> DSMBlock:
        """
        Compute DSM penalty for a single 15-min block.
        Returns a DSMBlock with all intermediate values (for transparency).
        """
        deviation_mw = actual_mw - schedule_mw
        deviation_pct = self.compute_deviation_pct(actual_mw, schedule_mw, avc_mw)
        band = self.solar_band if asset_type == "solar" else self.wind_band
        in_tolerance = abs(deviation_pct) <= band * 100

        if in_tolerance:
            penalty_inr = 0.0
            freq_multiplier = 0.0
        else:
            is_over = actual_mw > schedule_mw
            freq_multiplier = self._get_freq_multiplier(freq_hz, is_over)

            # Energy deviation in MWh (15-min block = 1/4 hour)
            deviation_mwh = abs(deviation_mw) / 4.0
            penalty_inr = deviation_mwh * ncd_inr_per_mwh * freq_multiplier

        return DSMBlock(
            block_no=0,  # caller sets this
            actual_mw=actual_mw,
            schedule_mw=schedule_mw,
            freq_hz=freq_hz,
            deviation_mw=deviation_mw,
            deviation_pct=deviation_pct,
            in_tolerance=in_tolerance,
            freq_multiplier=freq_multiplier,
            penalty_inr=penalty_inr,
        )

    def compute_expected_penalty(self,
                                  quantile_forecasts: Dict[float, float],
                                  schedule_mw: float,
                                  avc_mw: float,
                                  freq_hz: float,
                                  ncd_inr_per_mwh: float,
                                  asset_type: str = "solar") -> float:
        """
        Probability-weighted expected ₹ penalty across all forecast quantiles.
        This is the KEY function that links ML uncertainty to financial risk.

        quantile_forecasts: {0.05: 10.2, 0.10: 12.1, ..., 0.95: 48.3}
        Each quantile = one equally-likely scenario of actual generation.
        """
        penalties = []
        for q, actual_mw in quantile_forecasts.items():
            block = self.compute_block_penalty(
                actual_mw, schedule_mw, avc_mw,
                freq_hz, ncd_inr_per_mwh, asset_type
            )
            penalties.append(block.penalty_inr)
        return float(np.mean(penalties))  # equal weight = 1/19 each

    def compute_day_penalties(self, quantile_forecast_df: pd.DataFrame,
                               schedule_mw_series: pd.Series,
                               avc_mw: float,
                               freq_hz_series: pd.Series,
                               ncd_inr_per_mwh: float,
                               asset_type: str = "solar") -> pd.DataFrame:
        """
        Compute expected ₹ penalty for all 96 blocks of a day.
        Returns DataFrame with per-block penalty breakdown.
        """
        results = []
        q_cols = [c for c in quantile_forecast_df.columns]
        q_levels = [int(c[1:]) / 100 for c in q_cols]

        for i, (idx, row) in enumerate(quantile_forecast_df.iterrows()):
            block_no = i + 1
            schedule = float(schedule_mw_series.iloc[i])
            freq = float(freq_hz_series.iloc[i]) if freq_hz_series is not None else 50.0
            q_dict = {q: row[col] for q, col in zip(q_levels, q_cols)}

            exp_penalty = self.compute_expected_penalty(
                q_dict, schedule, avc_mw, freq, ncd_inr_per_mwh, asset_type
            )
            p50_block = self.compute_block_penalty(
                row["P50"], schedule, avc_mw, freq, ncd_inr_per_mwh, asset_type
            )
            results.append({
                "block_no": block_no,
                "timestamp": idx,
                "schedule_mw": schedule,
                "p50_actual_mw": row["P50"],
                "deviation_pct_at_p50": p50_block.deviation_pct,
                "in_tolerance_at_p50": p50_block.in_tolerance,
                "expected_penalty_inr": exp_penalty,
                "p50_penalty_inr": p50_block.penalty_inr,
            })

        df = pd.DataFrame(results)
        df["cumulative_expected_inr"] = df["expected_penalty_inr"].cumsum()
        return df
```

---

## Day 8 — Schedule Optimiser + Battery LP

```python
# backend/modules/optimize/schedule_optimizer.py

import numpy as np
import pandas as pd
from .battery_lp import BatteryLP

def optimize_day_schedule(quantile_forecast_df: pd.DataFrame,
                           avc_mw: float,
                           dsm_engine,
                           ncd_inr_per_mwh: float,
                           asset_type: str = "solar",
                           freq_hz: float = 50.0,
                           step_mw: float = 0.5) -> pd.DataFrame:
    """
    For each 15-min block, grid-search the schedule S ∈ [0, AvC]
    that minimises expected ₹ penalty across all quantile scenarios.
    No battery: each block is independent.
    """
    q_cols = [c for c in quantile_forecast_df.columns]
    q_levels = [int(c[1:]) / 100 for c in q_cols]
    candidates = np.arange(0, avc_mw + step_mw, step_mw)

    optimised_schedules = []
    for i, (idx, row) in enumerate(quantile_forecast_df.iterrows()):
        q_dict = {q: row[col] for q, col in zip(q_levels, q_cols)}
        best_s, best_cost = None, float("inf")

        for s in candidates:
            cost = dsm_engine.compute_expected_penalty(
                q_dict, s, avc_mw, freq_hz, ncd_inr_per_mwh, asset_type
            )
            if cost < best_cost:
                best_cost, best_s = cost, s

        # Naive P50 schedule cost (baseline comparison)
        p50_naive_cost = dsm_engine.compute_expected_penalty(
            q_dict, row["P50"], avc_mw, freq_hz, ncd_inr_per_mwh, asset_type
        )
        optimised_schedules.append({
            "block_no": i + 1,
            "timestamp": idx,
            "p50_schedule_mw": row["P50"],
            "optimised_schedule_mw": best_s,
            "naive_expected_inr": p50_naive_cost,
            "optimised_expected_inr": best_cost,
            "savings_inr": p50_naive_cost - best_cost,
        })

    df = pd.DataFrame(optimised_schedules)
    df["total_naive_inr"] = df["naive_expected_inr"].sum()
    df["total_optimised_inr"] = df["optimised_expected_inr"].sum()
    df["total_savings_inr"] = df["savings_inr"].sum()
    df["savings_pct"] = (df["savings_inr"].sum() /
                          max(df["naive_expected_inr"].sum(), 1)) * 100
    return df
```

```python
# backend/modules/optimize/battery_lp.py

import pulp
import numpy as np
import pandas as pd

class BatteryLP:
    """
    96-block battery dispatch optimiser using PuLP + CBC solver.
    Minimises expected DSM penalty across the day jointly with battery dispatch.
    """

    def __init__(self, capacity_mwh: float, max_charge_mw: float,
                  max_discharge_mw: float, efficiency_charge: float = 0.92,
                  efficiency_discharge: float = 0.92,
                  soc_min_mwh: float = 0.05, soc_initial_mwh: float = None,
                  degradation_cost_inr_per_mwh: float = 500):
        self.capacity = capacity_mwh
        self.p_charge_max = max_charge_mw
        self.p_discharge_max = max_discharge_mw
        self.eta_c = efficiency_charge
        self.eta_d = efficiency_discharge
        self.soc_min = soc_min_mwh
        self.soc_initial = soc_initial_mwh or capacity_mwh * 0.5
        self.deg_cost = degradation_cost_inr_per_mwh

    def optimise(self, quantile_forecast_df: pd.DataFrame,
                  avc_mw: float, dsm_engine,
                  ncd_inr_per_mwh: float,
                  asset_type: str = "solar") -> pd.DataFrame:
        """
        Solve the 96-block LP:
        Minimise: sum_t(expected_DSM_penalty(schedule_t)) + degradation_cost
        Subject to: battery SOC, power, and schedule constraints.
        """
        T = len(quantile_forecast_df)  # 96 blocks
        prob = pulp.LpProblem("BatteryDispatch", pulp.LpMinimize)

        # Decision variables
        charge = [pulp.LpVariable(f"c_{t}", 0, self.p_charge_max) for t in range(T)]
        discharge = [pulp.LpVariable(f"d_{t}", 0, self.p_discharge_max) for t in range(T)]
        soc = [pulp.LpVariable(f"soc_{t}", self.soc_min, self.capacity) for t in range(T)]

        # Linearised penalty per block (slope approximation around P50)
        # This is the key approximation: use P50 penalty slope for LP
        penalty_slopes = []
        for i, (_, row) in enumerate(quantile_forecast_df.iterrows()):
            p50 = row["P50"]
            # Approximate: penalty sensitivity at P50
            delta = 0.5  # MW
            cost_up = dsm_engine.compute_expected_penalty(
                {q: row[col] for q, col in zip(
                    [int(c[1:])/100 for c in quantile_forecast_df.columns],
                    quantile_forecast_df.columns
                )},
                p50 + delta, avc_mw, 50.0, ncd_inr_per_mwh, asset_type
            )
            cost_dn = dsm_engine.compute_expected_penalty(
                {q: row[col] for q, col in zip(
                    [int(c[1:])/100 for c in quantile_forecast_df.columns],
                    quantile_forecast_df.columns
                )},
                p50 - delta, avc_mw, 50.0, ncd_inr_per_mwh, asset_type
            )
            slope = (cost_up - cost_dn) / (2 * delta)
            penalty_slopes.append(slope)

        # Objective: minimise total penalty + degradation cost
        penalty_terms = [slope * discharge[t] for t, slope in enumerate(penalty_slopes)]
        degradation_terms = [(charge[t] + discharge[t]) * self.deg_cost / 4
                              for t in range(T)]
        prob += pulp.lpSum(penalty_terms) + pulp.lpSum(degradation_terms)

        # SOC dynamics constraints
        prob += soc[0] == (self.soc_initial
                           + self.eta_c * charge[0] / 4
                           - discharge[0] / (self.eta_d * 4))
        for t in range(1, T):
            prob += soc[t] == (soc[t-1]
                               + self.eta_c * charge[t] / 4
                               - discharge[t] / (self.eta_d * 4))

        # End-of-day SOC: return to at least initial
        prob += soc[T-1] >= self.soc_min

        # Cannot charge and discharge simultaneously (binary not needed for LP)
        # LP relaxation is valid since we use separate variables with cost signal

        # Solve
        prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=30))

        results = []
        for t in range(T):
            results.append({
                "block_no": t + 1,
                "charge_mw": pulp.value(charge[t]),
                "discharge_mw": pulp.value(discharge[t]),
                "soc_mwh": pulp.value(soc[t]),
            })
        return pd.DataFrame(results)
```

---

## Day 9–10 — Backtesting + DSM Validation (Notebooks 08, 09)

```python
# Notebook 08: Rolling-origin backtest

def rolling_origin_backtest(df: pd.DataFrame, feature_cols: list,
                              target_col: str, model_class,
                              train_days: int = 60, test_days: int = 14,
                              step_days: int = 1):
    """
    Walk-forward backtest. Never uses future data in training.
    Evaluates per horizon band: 0-6h, 6-12h, 12-24h, 24-48h, 48-72h.
    """
    results = []
    all_dates = df.index.normalize().unique()

    for i in range(train_days, len(all_dates) - test_days, step_days):
        train_end = all_dates[i]
        test_start = all_dates[i]
        test_end = all_dates[min(i + test_days, len(all_dates) - 1)]

        train_mask = df.index.normalize() < train_end
        test_mask = (df.index.normalize() >= test_start) & \
                    (df.index.normalize() < test_end)

        X_train = df.loc[train_mask, feature_cols]
        y_train = df.loc[train_mask, target_col]
        X_test = df.loc[test_mask, feature_cols]
        y_test = df.loc[test_mask, target_col]

        model = model_class()
        # use last 20% of train as validation for early stopping
        split = int(len(X_train) * 0.8)
        model.train(X_train.iloc[:split], y_train.iloc[:split],
                    X_train.iloc[split:], y_train.iloc[split:])

        preds = model.predict(X_test)
        results.append({
            "fold_start": test_start,
            "predictions": preds,
            "actuals": y_test,
        })

    return results

def compute_all_metrics(results: list, avc_mw: float):
    """Compute MAE, RMSE, CRPS, Pinball, PICP per horizon band."""
    all_preds = pd.concat([r["predictions"] for r in results])
    all_actuals = pd.concat([r["actuals"] for r in results])

    metrics = {}
    # Point accuracy
    metrics["MAE"] = np.mean(np.abs(all_actuals - all_preds["P50"]))
    metrics["nMAE"] = metrics["MAE"] / avc_mw
    metrics["RMSE"] = np.sqrt(np.mean((all_actuals - all_preds["P50"])**2))
    # PICP (80% interval)
    in_80 = ((all_actuals >= all_preds["P10"]) &
              (all_actuals <= all_preds["P90"]))
    metrics["PICP_80"] = in_80.mean()
    # Pinball loss per quantile
    for col in all_preds.columns:
        q = int(col[1:]) / 100
        err = all_actuals - all_preds[col]
        metrics[f"Pinball_{col}"] = np.mean(
            np.where(err >= 0, q * err, (q-1) * err)
        )
    return metrics
```

---

## Day 11 — Evaluation Report (Notebook 11)

Key outputs for the judges:

1. **Model comparison table**: Persistence vs LightGBM vs Chronos-2 (MAE, CRPS, PICP, Pinball)
2. **₹ savings chart**: Expected penalty (submit P50) vs Optimised schedule — show actual ₹ saved per day
3. **Reliability diagram**: Plot empirical quantile coverage vs stated quantile
4. **SHAP feature importance**: Top 15 features driving forecasts
5. **Pooling analysis**: Individual plant ₹ vs pooled ₹ — reproduce Prayas 30–65% finding

---

## Critical Things NEVER to Do

| ❌ WRONG | ✅ RIGHT |
|---|---|
| Include `ALLSKY_KT` (clear-sky ratio from NASA POWER) as a feature | Compute clear-sky index from raw GHI ÷ pvlib clear-sky GHI |
| Use `gen_lag_24` for 24h ahead forecast | Use `gen_lag_96` minimum (96 blocks = 24h) |
| Train and test on same date range | Always walk-forward: train on past, test on future |
| Let LLM output ₹ values | DSM engine always computes ₹; LLM only explains |
| Use ERA5 reanalysis for training weather features | Use Open-Meteo Previous Runs (as-issued forecast) |
| Pool X_train and X_val before early stopping | Keep val strictly after train in time |

---

## Handoff Checklist (What You Give Member 2)

```
✅ backend/modules/forecast/physics.py       (complete, tested)
✅ backend/modules/forecast/features.py      (complete, tested)
✅ backend/modules/forecast/lgbm_model.py    (complete, tested)
✅ backend/modules/forecast/chronos_model.py (complete, tested)
✅ backend/modules/forecast/persistence.py   (complete, tested)
✅ backend/modules/forecast/ensemble.py      (model selector)
✅ backend/modules/forecast/calibration.py   (PICP check)
✅ backend/modules/dsm/engine.py             (complete, unit tested)
✅ backend/modules/dsm/config_loader.py      (YAML loader)
✅ backend/modules/optimize/schedule_optimizer.py
✅ backend/modules/optimize/battery_lp.py
✅ sample_forecast_output.json               (for Member 3 mock data)
✅ models/lgbm_champion_GJ_SOLAR_A.pkl       (trained model file)
✅ models/power_curve_GJ_WIND_C.pkl          (fitted wind curve)
```
