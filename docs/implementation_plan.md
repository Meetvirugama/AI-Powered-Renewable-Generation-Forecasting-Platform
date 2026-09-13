# End-to-End Implementation Plan
## AI-Powered Renewable Generation Forecasting Platform
### Hackathon Edition — Predict → Price in ₹ → Optimise → Act → Explain

---

> [!NOTE]
> **Historical reference document.** This was the master planning spec written at project start.
> It has been largely superseded by narrower, more accurate docs as the codebase was built.
> Prefer these instead:
>
> | Topic | Read instead |
> |---|---|
> | What & Why | `docs/project_understanding.md` |
> | System architecture + DB schema | `docs/system_architecture.md` |
> | ML pipeline status | `docs/ml_pipeline.md` |
> | Model integration blockers | `docs/model_integration.md` |
> | What remains to do | `docs/roadmap.md` |
> | API contract (RAG) | `docs/api_rag_contract.md` |
> | Frontend sprints | `docs/frontend_implementation_plan.md` |
> | Deploy + ops | `docs/deployment_azure.md` · `docs/runbook.md` (AWS path: `docs/deployment.md`) |
>
> This file is kept because it contains original design rationale not captured elsewhere.
>
> Where the build departed from this plan (Chronos-2 not built, the battery LP replaced by a
> recourse model, 19 quantiles reduced to 3 calibrated ones, AWS replaced by Azure), the reasons
> are in `docs/project_understanding.md` under *How the build differed from the original plan*.


## Table of Contents
1. [Project Mission & What Makes This Win](#1-project-mission)
2. [Reference Repo Analysis & What We Reuse](#2-reference-repo-analysis)
3. [Complete Folder Structure](#3-complete-folder-structure)
4. [Phase 1 — Data Ingestion & Quality Pipeline](#4-phase-1)
5. [Phase 2 — Physics + ML Forecasting Engine](#5-phase-2)
6. [Phase 3 — DSM Engine + Schedule Optimiser](#6-phase-3)
7. [Phase 4 — React Dashboard + RAG Copilot](#7-phase-4)
8. [Phase 5 — Cloud Deployment & CI/CD](#8-phase-5)
9. [Database Schema](#9-database-schema)
10. [API Contract](#10-api-contract)
11. [Config & Secret Management](#11-config--secret-management)
12. [Evaluation & Validation Plan](#12-evaluation--validation-plan)
13. [Disclosures & Known Limitations](#13-disclosures)
14. [Technology Stack Summary](#14-technology-stack)
15. [Delivery Timeline](#15-delivery-timeline)

---

## 1. Project Mission

> **The forecast is the input to the deliverable. The deliverable is the decision.**

Most submissions will produce a point forecast and a chart. We go further:

```
Weather Forecast
       ↓
Physics (pvlib + wind curve) → ML correction (LightGBM quantile + Chronos-2)
       ↓
Calibrated P10 / P50 / P90 per 15-min block (96–288 blocks)
       ↓
DSM Engine (CERC 2024/2026 seller rules, YAML-configured)
→ Expected ₹ penalty across 19 quantile scenarios
       ↓
Optimiser (NumPy grid search + PuLP/CBC battery LP)
→ Schedule + battery dispatch that MINIMISES expected ₹
       ↓
Action Cards: battery plan, curtailment advisory, reserve flag
       ↓
RAG Copilot: LLM explains using retrieved CERC clause + page, never invents numbers
```

**The unique combination nobody else has built:**
Probabilistic forecast → rupee penalty → optimised schedule → grid action → pooling → explainable regulatory citation.

---

## 2. Reference Repo Analysis

### 2a. `Nibiru7899/solar-forecasting-chronos`

**What it is:** 14-notebook pipeline for next-day solar irradiance forecasting across 50 Indian cities using Chronos-2 (zero-shot + fine-tuned), LSTM, SARIMA, Transformer/Informer baselines. Includes a Gradio app.

**Notebooks:**

| # | Notebook | Purpose | Our Action |
|---|---|---|---|
| 01 | `data_acquisition.ipynb` | NASA POWER API for 50 Indian cities | ✅ Adapt — same API, our city list |
| 02 | `preprocessing_feature_engineering.ipynb` | Resampling, gap fill, solar geometry | ✅ Adapt — add 15-min blocks for DSM |
| 03 | `eda_visualization.ipynb` | EDA across cities | Reference only |
| 04 | `baseline_persistence_arima.ipynb` | Persistence + SARIMA | ✅ Reuse persistence baseline logic |
| 05 | `baseline_lstm.ipynb` | LSTM | Skip — LightGBM is better for tabular |
| 06 | `baseline_transformer_informer.ipynb` | Transformer | Skip |
| 07 | `chronos2_zeroshot.ipynb` | Chronos-2 zero-shot on Indian cities | ✅ Direct reuse as starting point |
| 08 | `chronos2_finetuning.ipynb` | Fine-tune Chronos on Indian irradiance | ✅ Adapt for plant-level generation |
| 09 | `fewshot_experiments.ipynb` | Few-shot cross-city | Reference for cold-start plants |
| 10 | `cross_climate_analysis.ipynb` | Generalization across Indian climates | ✅ Gujarat plant setup |
| 11 | `evaluation_comparison.ipynb` | MAE, CRPS, WQL, MASE all models | ✅ Reuse metrics framework |
| 12 | `iems_prototype.ipynb` | Integrated energy mgmt prototype | Reference |
| 13 | `unseen_city_validation.ipynb` | Zero-shot on unseen cities | ✅ For new plant cold-start |
| 14 | `finetuned_chronos_unseen.ipynb` | Fine-tuned + unseen | ✅ Reuse |

**Reusable utility modules:**
- `utils/data_utils.py` — NASA POWER fetching, preprocessing pipeline
- `utils/feature_engineering.py` — solar position, clear-sky index, seasonal features
- `utils/metrics.py` — CRPS, pinball loss, MASE, WQL already implemented
- `utils/normalization.py` — scaling pipeline for Chronos input format
- `utils/city_config.py` — 50 Indian city lat/lon/timezone configs

**What is MISSING (we build):**
- ❌ No 15-minute block output (it's daily/hourly irradiance only)
- ❌ No Open-Meteo as-issued weather forecast features (uses NASA POWER historical only)
- ❌ No LightGBM quantile model (uses LSTM/SARIMA as ML baselines)
- ❌ No wind generation at all
- ❌ No pvlib physics-based generation simulation
- ❌ No DSM engine, no ₹ penalty, no schedule optimiser
- ❌ No battery LP
- ❌ No FastAPI backend, no React dashboard
- ❌ No RAG copilot

---

### 2b. `elinaparajuli/DSM-calculation-2024`

**What it is:** A Jupyter notebook with a real SLDC dataset (March 2024, 2,976 rows = 31 days × 96 blocks/day). Implements a **buyer-side** (discom) DSM calculator using NCD × frequency-band multipliers.

**Data schema (real SLDC data):**
```
Date | Time | Block (1–96) | Freq (Hz) | Actual (MW) | Schedule (MW)
| Deviation (MW) | Deviation (%) | NCD (₹/MWh) | Actual_ERPC
```

**What it implements correctly:**

| Rule | Implemented? |
|---|---|
| Frequency bands: `<49.90`, `49.90–49.95`, `49.95–50.03` (normal), `50.03–50.05`, `≥50.05` | ✅ Yes |
| Overdraw (actual > schedule for buyers) | ✅ Yes |
| Underdraw (actual < schedule for buyers) | ✅ Yes |
| Zero-schedule cases | ✅ Yes |
| ≥50.05 Hz → ₹0 for over-injection | ✅ Yes |
| Frequency multipliers (1.5×, 1.0×, 0.75× etc.) | ✅ Yes |

**What is WRONG / MISSING for our use case:**

| Gap | Detail |
|---|---|
| ❌ Buyer-side only | Designed for discoms importing power. Our users are **renewable generators (sellers)** |
| ❌ No X-trajectory | Missing the 2026 CERC order X = 100%→90%→75%→55%→30%→0 by April 2031 |
| ❌ No tolerance bands | Missing ±10%→±5% solar / ±15%→±10% wind band narrowing |
| ❌ Wrong deviation formula | Doesn't use `Deviation% = 100×(A−S)/(X·AvC + (1−X)·S)` |
| ❌ No AvC denominator | Uses NCD (buyer denominator); generators use AvC-based denominator |
| ❌ Hardcoded NCD from CSV | NCD must be fetched from NLDC/POSOCO or parameterised |
| ❌ No YAML config | Rules hardcoded; can't switch 2024/2026/2031 rule sets at runtime |
| ❌ No probabilistic output | Computes deterministic penalty; no expected ₹ across 19 quantile scenarios |
| ❌ No pooling | No portfolio-level deviation aggregation |
| ❌ No optimiser integration | Doesn't search for the optimal schedule |

**Conclusion:** Use as a **reference for frequency-band logic and data schema only**. Build our DSM engine fresh as `dsm/engine.py` with YAML-driven configuration.

---

## 3. Complete Folder Structure

```
AI-Powered-Renewable-Generation-Forecasting-Platform/
│
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
│
├── config/
│   ├── dsm_rules_2024.yaml          # CERC DSM 2024 baseline (seller-side)
│   ├── dsm_rules_2026.yaml          # 2026 amendment: X-trajectory + tighter bands
│   ├── dsm_rules_2031.yaml          # End-state: X=0, ±5% solar, ±10% wind
│   ├── plants.yaml                  # Demo Gujarat plants (coords, AvC, pool ID)
│   └── settings.yaml                # App-level settings
│
├── backend/
│   ├── main.py                      # FastAPI app entry point
│   │
│   ├── api/                         # Route handlers
│   │   ├── __init__.py
│   │   ├── plants.py                # GET /plants, GET /plants/{id}
│   │   ├── forecast.py              # GET /forecast?plant_id&date
│   │   ├── dsm.py                   # POST /dsm  (compute penalty for a schedule)
│   │   ├── optimize.py              # POST /optimize  (find min-₹ schedule)
│   │   ├── pooling.py               # POST /pooling  (what-if pooling simulator)
│   │   ├── rag.py                   # POST /rag/query
│   │   ├── dashboard.py             # GET /dashboard/{plant_id}
│   │   └── pipeline.py              # POST /pipeline/run  (trigger daily pipeline)
│   │
│   ├── modules/
│   │   │
│   │   ├── forecast/
│   │   │   ├── __init__.py
│   │   │   ├── physics.py           # pvlib solar geometry + wind power curve
│   │   │   ├── features.py          # Feature engineering (lags, clear-sky, time)
│   │   │   ├── lgbm_model.py        # LightGBM quantile regression (P05–P95)
│   │   │   ├── chronos_model.py     # Chronos-2-small wrapper
│   │   │   ├── persistence.py       # Persistence baseline (yesterday same block)
│   │   │   ├── ensemble.py          # Model selection + weighted ensemble
│   │   │   └── calibration.py       # Quantile calibration, reliability diagrams
│   │   │
│   │   ├── dsm/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py            # Core DSM engine (CERC seller rules)
│   │   │   ├── config_loader.py     # YAML config loader + X-trajectory resolver
│   │   │   └── pooling.py           # Portfolio pooling deviation aggregator
│   │   │
│   │   ├── optimize/
│   │   │   ├── __init__.py
│   │   │   ├── schedule_optimizer.py  # NumPy grid search (no battery)
│   │   │   └── battery_lp.py          # PuLP + CBC 96-block battery LP
│   │   │
│   │   ├── rag/
│   │   │   ├── __init__.py
│   │   │   ├── ingest.py            # PyMuPDF parsing, clause-aware chunking
│   │   │   ├── embed.py             # bge-m3 embeddings
│   │   │   ├── retriever.py         # BM25 + pgvector hybrid + bge-reranker
│   │   │   ├── cache.py             # LLM response cache (Redis or in-memory)
│   │   │   └── copilot.py           # LangGraph agent + LiteLLM (Groq/Gemini)
│   │   │
│   │   └── pipeline/
│   │       ├── __init__.py
│   │       └── daily.py             # Orchestrates full 9-step daily pipeline
│   │
│   ├── data/
│   │   ├── ingestion/
│   │   │   ├── __init__.py
│   │   │   ├── openmeteo.py         # Open-Meteo Forecast API (next 24–72h, LIVE)
│   │   │   ├── openmeteo_historical.py  # Open-Meteo Previous Runs (as-issued, OFFLINE)
│   │   │   └── nasa_power.py        # NASA POWER India Solar Benchmark (OFFLINE)
│   │   │
│   │   ├── quality/
│   │   │   ├── __init__.py
│   │   │   ├── validator.py         # Missing values, outliers, leakage checks, AvC flag
│   │   │   └── resampler.py         # 15-min resampling, UTC→IST, unit normalisation
│   │   │
│   │   └── simulation/
│   │       ├── __init__.py
│   │       ├── solar_sim.py         # pvlib: GHI→POA→DC→AC, cell-temp derating
│   │       └── wind_sim.py          # Turbine power curve fit + wind speed → MW
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py                # SQLAlchemy ORM models (all tables)
│   │   ├── session.py               # DB session management
│   │   └── migrations/              # Alembic migration scripts
│   │       └── env.py
│   │
│   └── core/
│       ├── __init__.py
│       ├── config.py                # Pydantic BaseSettings (reads .env)
│       ├── logging.py               # Structured JSON logging
│       └── security.py              # API key auth dependency
│
├── colab_notebooks/                 # Google Colab T4 — offline training + backtests
│   ├── 01_data_acquisition.ipynb        # NASA POWER + Open-Meteo Historical pull
│   ├── 02_preprocessing.ipynb           # Quality layer, 15-min alignment
│   ├── 03_physics_simulation.ipynb      # pvlib solar + wind sim → demo-plant MW
│   ├── 04_feature_engineering.ipynb     # Full feature set construction
│   ├── 05_lgbm_quantile.ipynb           # LightGBM quantile training + SHAP
│   ├── 06_chronos2_zeroshot.ipynb       # Zero-shot Chronos-2 on our plants
│   ├── 07_chronos2_finetune.ipynb       # Fine-tune on Indian plant data (LoRA*)
│   ├── 08_backtesting.ipynb             # Rolling-origin backtest harness
│   ├── 09_dsm_engine_test.ipynb         # DSM engine vs known SLDC cases
│   ├── 10_rag_embed.ipynb               # bge-m3 → pgvector for regulation corpus
│   └── 11_evaluation_report.ipynb       # MAE, CRPS, PICP, pinball loss, ₹ savings
│
├── frontend/                        # React dashboard
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── components/
│   │   │   ├── PlantMap.jsx             # Gujarat plant locations + live status
│   │   │   ├── ForecastFanChart.jsx     # P10/P50/P90 band chart (Recharts/D3)
│   │   │   ├── RiskHeatmap.jsx          # 96-block ₹ exposure heatmap
│   │   │   ├── ScheduleComparison.jsx   # Submit-P50 vs Optimised ₹ bar chart
│   │   │   ├── RegulationSlider.jsx     # 2026→2031 rule-year slider (re-runs DSM)
│   │   │   ├── PoolingToggle.jsx        # Individual vs pooled ₹ what-if
│   │   │   ├── ActionCards.jsx          # Battery / curtailment / reserve cards
│   │   │   └── RAGCopilot.jsx           # Chat panel with cited CERC answers
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx            # Main operator view
│   │   │   ├── PlantDetail.jsx          # Per-plant deep dive
│   │   │   └── Backtest.jsx             # Historical backtest results
│   │   ├── hooks/
│   │   │   ├── useForecast.js
│   │   │   ├── useDSM.js
│   │   │   └── useRAG.js
│   │   ├── api/
│   │   │   └── client.js                # Axios API client
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
│
├── regulations/                     # CERC/IEGC PDFs for RAG corpus
│   ├── CERC_DSM_Regulations_2024.pdf
│   ├── CERC_DSM_Amendment_2026.pdf
│   └── IEGC_2023.pdf
│
├── tests/
│   ├── __init__.py
│   ├── test_dsm_engine.py           # Unit tests: all frequency bands × deviation cases
│   ├── test_physics.py              # pvlib solar + wind curve correctness
│   ├── test_optimizer.py            # Schedule + battery LP feasibility
│   ├── test_calibration.py          # PICP checks on holdout data
│   └── test_api.py                  # FastAPI route smoke tests
│
├── infra/
│   ├── terraform/
│   │   ├── main.tf                  # VPC, EC2, RDS, S3, CloudFront, ALB
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── docker/
│       └── nginx.conf
│
└── .github/
    └── workflows/
        ├── ci.yml                   # Lint (ruff) + tests + docker build + image scan
        └── deploy.yml               # OIDC → ECR push → SSM RunCommand → EC2 deploy
```

---

## 4. Phase 1 — Data Ingestion & Quality Pipeline

### 4.1 Data Sources

| Source | Data | Licence | Mode |
|---|---|---|---|
| Open-Meteo Forecast API | Next 24–72h: GHI, DNI, DHI, wind speed/dir, temp, humidity | Free, no key | LIVE |
| Open-Meteo Historical Forecast (Previous Runs) | Weather AS-ISSUED from 2021 (model inputs for training) | Free, CC BY 4.0 | OFFLINE |
| NASA POWER India Solar Benchmark | 4.38M hourly rows, 50 Indian cities, 2016–2025 | CC BY 4.0 | OFFLINE |
| Kaggle Solar Power Generation Data | 2 Indian plants, 34 days real inverter-level data | Free | OFFLINE (validation) |
| CARE Wind Farm A | Real turbine power vs wind speed | CC BY-SA 4.0 | OFFLINE (curve fit) |
| CERC DSM Regulations 2024 + 2026, IEGC 2023 | PDFs for RAG corpus | Public | OFFLINE (build index) |

### 4.2 Open-Meteo Forecast API — Variables We Pull

```python
# Variables fetched per plant location (lat, lon)
hourly_variables = [
    "shortwave_radiation",        # GHI (W/m²)
    "direct_normal_irradiance",   # DNI (W/m²)
    "diffuse_radiation",          # DHI (W/m²)
    "global_tilted_irradiance",   # GTI (W/m²) — plane-of-array proxy
    "wind_speed_10m",             # m/s
    "wind_speed_80m",             # m/s (hub height proxy)
    "wind_speed_120m",            # m/s
    "wind_direction_10m",         # degrees
    "temperature_2m",             # °C
    "relative_humidity_2m",       # %
    "precipitation",              # mm
    "sunshine_duration",          # seconds
    "cloud_cover",                # %
]
# Forecast horizon: next 72 hours (288 × 15-min blocks after interpolation)
# Interpolation: hourly → 15-min linear for all variables
# UTC stored, IST displayed
```

### 4.3 Feature Engineering Pipeline

```
Raw weather features
    + Solar position (pvlib: zenith, azimuth, elevation)
    + Clear-sky irradiance (Ineichen model via pvlib)
    + Clear-sky index = GHI / clear-sky GHI
    + Plane-of-array irradiance (transposition: tilt + azimuth per site)
    + Cell temperature (Faiman model)
    + Indian season encoding (summer/monsoon/post-monsoon/winter)
    + Hour-of-day, day-of-year, is_holiday
    + Historical generation lags (≥ forecast horizon to prevent leakage)
    + Rolling means (1h, 3h, 24h) of generation
    + Site metadata: AvC, tilt, azimuth, pool_id, tech (solar/wind)
    ↓
Model-ready feature matrix (15-min blocks)
```

### 4.4 Data Quality Rules

| Check | Rule | Action |
|---|---|---|
| Timestamps | All stored in UTC, displayed in IST (UTC+5:30) | Convert on ingest |
| Missing values | < 10% gap: forward-fill; ≥ 10% gap: flag as reduced-confidence | Flag in output |
| Generation > AvC | Flag but do NOT clip (actuals can exceed AvC; scheduling cannot) | Flag only |
| 15-min resampling | Hourly → 15-min via linear interpolation | Apply always |
| Leakage check | No feature uses any data from after the forecast issue cutoff | Assert at training |
| Negative generation | Set to zero (nighttime noise) | Zero-fill |
| Unit normalisation | Everything in MW, MWh, °C, m/s | Enforce on ingest |

### 4.5 Demo Plants (`config/plants.yaml`)

```yaml
plants:
  - id: GJ_SOLAR_A
    name: "Gujarat Solar Plant A"
    type: solar
    lat: 23.2156
    lon: 72.6369          # near Gandhinagar
    avc_mw: 50.0          # Authorised Generation Capacity
    tilt_deg: 22.0
    azimuth_deg: 180.0    # south-facing
    pool_id: GJ_POOL_1
    technology: mono_perc

  - id: GJ_SOLAR_B
    name: "Gujarat Solar Plant B"
    type: solar
    lat: 22.3039
    lon: 70.8022          # near Rajkot
    avc_mw: 75.0
    tilt_deg: 20.0
    azimuth_deg: 180.0
    pool_id: GJ_POOL_1
    technology: mono_perc

  - id: GJ_WIND_C
    name: "Gujarat Wind Farm C"
    type: wind
    lat: 23.6102
    lon: 68.9761          # near Kutch (high wind resource)
    avc_mw: 40.0
    hub_height_m: 120.0
    rotor_diameter_m: 130.0
    pool_id: GJ_POOL_1
    power_curve: care_wind_farm_a_fitted

  - id: GJ_SOLAR_D
    name: "Gujarat Solar Plant D"
    type: solar
    lat: 24.1858
    lon: 72.4337          # near Palanpur
    avc_mw: 30.0
    tilt_deg: 23.0
    azimuth_deg: 180.0
    pool_id: GJ_POOL_2
    technology: bifacial
```

---

## 5. Phase 2 — Physics + ML Forecasting Engine

### 5.1 Physics Layer (`modules/forecast/physics.py`)

**Solar (pvlib):**
```
1. Sun position: solarposition(lat, lon, timestamp)
2. Clear-sky GHI: Ineichen model
3. POA irradiance: irradiance.get_total_irradiance(tilt, azimuth, DNI, GHI, DHI)
4. Cell temperature: Faiman model (T_cell = T_amb + POA × (0.0342 − 0.00252 × wind))
5. DC power: simple efficiency model (η × POA × area)
6. AC power: inverter model (clipped at AvC)
→ Output: expected_generation_MW per 15-min block
```

**Wind (power curve):**
```
1. Hub-height wind: extrapolate from 10m/80m/120m using power law (α = 0.143)
2. Air density correction: ρ_actual / ρ_standard
3. Power curve lookup: fit sigmoid on CARE Wind Farm A data (wind_speed → MW)
4. Apply AvC clipping (but flag, don't drop)
→ Output: expected_generation_MW per 15-min block
```

### 5.2 LightGBM Quantile Model (`modules/forecast/lgbm_model.py`)

```python
# One model per quantile level (19 levels: P05, P10, ..., P95)
# Or: single model with quantile as a feature (faster, slightly less accurate)
# Strategy: train separate models per quantile for P10, P50, P90 for demo;
#           full 19-level in Colab notebook

params = {
    "objective": "quantile",
    "alpha": q,              # quantile level e.g. 0.10
    "learning_rate": 0.05,
    "n_estimators": 500,
    "num_leaves": 63,
    "min_child_samples": 20,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
}

# Post-processing: isotonic regression sort to prevent quantile crossing
# Output: DataFrame [block_id, P05, P10, ..., P95]
```

**Features fed to LightGBM:**
- Physics model output (`expected_generation_MW`) — primary feature
- All weather forecast variables
- Solar geometry features
- Clear-sky index
- Time features (hour, day_of_year, season)
- Historical generation lags (lag ≥ forecast horizon, NO leakage)
- Site metadata (one-hot encoded plant type, pool_id)

### 5.3 Chronos-2 Model (`modules/forecast/chronos_model.py`)

```python
# Using: amazon/chronos-t5-small (28M params, stays within T4 GPU RAM)
# Zero-shot first; fine-tuned checkpoint if available from Colab

from chronos import ChronosPipeline

pipeline = ChronosPipeline.from_pretrained(
    "amazon/chronos-t5-small",
    device_map="cuda",
    torch_dtype=torch.bfloat16,
)

# Known future covariates = weather forecast features (Chronos-2 supports this)
# Context: last 7 days of generation history (672 blocks @ 15-min)
# Prediction length: 96 blocks (24h) or 288 blocks (72h)
# Output: quantile forecasts via pipeline.predict() with num_samples=500
```

### 5.4 Persistence Baseline (`modules/forecast/persistence.py`)

```python
# Two variants:
# 1. Yesterday-same-block: forecast[t] = actual[t - 96 blocks]
# 2. Clear-sky scaled: scale yesterday's generation by today's clear-sky ratio

def persistence_forecast(history_df, date, plant):
    yesterday = history_df[history_df.date == date - 1d]
    return yesterday["generation_mw"].values  # 96 blocks

def clear_sky_scaled_persistence(history_df, clear_sky_today, clear_sky_yesterday, ...):
    scale = clear_sky_today / (clear_sky_yesterday + 1e-6)
    return yesterday_gen * np.clip(scale, 0, 2)
```

### 5.5 Model Selection & Ensemble (`modules/forecast/ensemble.py`)

```
Rolling-origin backtest (offline, Colab):
  - Walk-forward: train on t-N days, forecast t, advance by 1 day
  - Evaluate: MAE, RMSE, Pinball Loss, CRPS, PICP per horizon band
  - Compare: Persistence vs LightGBM vs Chronos-2 (zero-shot) vs Chronos-2 (fine-tuned)
  - Select: champion per site + horizon band by CRPS
  - Optional: weighted ensemble (softmax weights from val CRPS)

Live serving:
  - Load champion model checkpoint from S3
  - Fallback: persistence if model fails or data quality is degraded
```

### 5.6 Calibration (`modules/forecast/calibration.py`)

```python
# Reliability diagram: for each quantile q, check coverage
# Expected: P(actual ≤ P_q) ≈ q
# If miscalibrated: apply isotonic regression calibration on validation set

def compute_picp(forecasts, actuals, lower_q=0.10, upper_q=0.90):
    """Prediction Interval Coverage Probability"""
    in_interval = (actuals >= forecasts[lower_q]) & (actuals <= forecasts[upper_q])
    return in_interval.mean()  # Should be ~0.80 for 80% PI

def calibrate_quantiles(raw_quantiles, calibration_data):
    """Isotonic regression calibration"""
    # Apply per-quantile adjustment based on holdout coverage
    ...
```

---

## 6. Phase 3 — DSM Engine + Schedule Optimiser

### 6.1 CERC 2026 DSM Rules (Seller-Side, Renewable Generator)

**The key formula:**
```
Deviation% = 100 × (Actual_MW − Schedule_MW) / (X · AvC + (1 − X) · Schedule_MW)
```

Where `X` is the **tolerance factor** that decreases each year:

| Effective Date | X (Solar) | Solar Tolerance Band | Wind Tolerance Band |
|---|---|---|---|
| Apr 2026 | 1.00 | ±10% | ±15% |
| Oct 2026 | 0.90 | ±10% | ±15% |
| Oct 2027 | 0.75 | ±8% | ±12% |
| Oct 2028 | 0.55 | ±7% | ±11% |
| Oct 2030 | 0.30 | ±6% | ±10% |
| Apr 2031 | 0.00 | ±5% | ±10% |

**Penalty pricing (within/outside tolerance):**
```
If |Deviation%| ≤ Tolerance Band → ₹0 penalty
If |Deviation%| > Tolerance Band → NCD × Deviation_MWh × frequency_multiplier

Frequency multipliers (for over-injection/under-injection):
  f < 49.90 Hz:          multiplier = 2.0
  49.90 ≤ f < 49.95:     multiplier = 1.5
  49.95 ≤ f ≤ 50.03:     multiplier = 1.0   (normal)
  50.03 < f < 50.05:     multiplier = 0.75
  f ≥ 50.05 Hz:          over-injection price = ₹0  (curtailed, unpaid)
```

### 6.2 DSM YAML Config (`config/dsm_rules_2026.yaml`)

```yaml
rule_version: "CERC_DSM_2026"
effective_from: "2026-04-01"
seller_side: true
under_legal_challenge: true   # Delhi High Court — note in UI

x_trajectory:
  - from: "2026-04-01"; x: 1.00; solar_band: 0.10; wind_band: 0.15
  - from: "2026-10-01"; x: 0.90; solar_band: 0.10; wind_band: 0.15
  - from: "2027-10-01"; x: 0.75; solar_band: 0.08; wind_band: 0.12
  - from: "2028-10-01"; x: 0.55; solar_band: 0.07; wind_band: 0.11
  - from: "2030-10-01"; x: 0.30; solar_band: 0.06; wind_band: 0.10
  - from: "2031-04-01"; x: 0.00; solar_band: 0.05; wind_band: 0.10

frequency_multipliers:
  - freq_lt: 49.90;  over: 2.0;  under: 2.0
  - freq_gte: 49.90; freq_lt: 49.95; over: 1.5; under: 1.5
  - freq_gte: 49.95; freq_lte: 50.03; over: 1.0; under: 1.0
  - freq_gt: 50.03;  freq_lt: 50.05;  over: 0.75; under: 0.75
  - freq_gte: 50.05; over_injection_price: 0  # curtailed, zero payment

ncd_source: "POSOCO_daily"   # or "configurable_default"
ncd_default_inr_per_mwh: 450  # ₹/MWh default for demo
```

### 6.3 DSM Engine Logic (`modules/dsm/engine.py`)

```python
class DSMEngine:
    def __init__(self, config_path: str, rule_date: date):
        self.rules = load_yaml(config_path)
        self.x, self.band = self._get_x_and_band(rule_date)

    def compute_deviation_pct(self, actual_mw, schedule_mw, avc_mw):
        denom = self.x * avc_mw + (1 - self.x) * schedule_mw
        if denom == 0:
            return 0.0
        return 100 * (actual_mw - schedule_mw) / denom

    def compute_block_penalty(self, actual_mw, schedule_mw, avc_mw,
                               freq_hz, ncd_inr_per_mwh, asset_type):
        dev_pct = self.compute_deviation_pct(actual_mw, schedule_mw, avc_mw)
        deviation_mwh = (actual_mw - schedule_mw) / 4  # 15-min block

        # Check tolerance band
        band = self.rules["band"][asset_type]
        if abs(dev_pct) <= band * 100:
            return 0.0  # Within tolerance, no penalty

        # Over-injection at high frequency: zero payment
        if actual_mw > schedule_mw and freq_hz >= 50.05:
            return 0.0

        multiplier = self._get_freq_multiplier(freq_hz)
        penalty = deviation_mwh * ncd_inr_per_mwh * multiplier
        return penalty  # positive = payable by generator

    def compute_expected_penalty(self, quantile_forecasts, schedule_mw,
                                  avc_mw, freq_hz_scenario, ncd):
        """
        quantile_forecasts: dict {q_level: actual_mw} for 19 scenarios
        Returns: expected ₹ penalty (probability-weighted mean)
        """
        penalties = []
        for q, actual_mw in quantile_forecasts.items():
            p = self.compute_block_penalty(actual_mw, schedule_mw,
                                            avc_mw, freq_hz_scenario, ncd)
            penalties.append(p)
        return np.mean(penalties)  # equal-weight across quantiles
```

### 6.4 Portfolio Pooling (`modules/dsm/pooling.py`)

```python
# Prayas Energy Group finding: pooling cuts penalties 30–65%
# because independent forecast errors partially cancel at the pool level

def compute_pooled_deviation(plants_actual_mw: dict, plants_schedule_mw: dict,
                              pool_avc_mw: float, x: float):
    """
    Pool-level deviation uses sum of actuals and schedules.
    Errors cancel → lower net deviation % → lower penalty.
    """
    total_actual = sum(plants_actual_mw.values())
    total_schedule = sum(plants_schedule_mw.values())
    pool_denom = x * pool_avc_mw + (1 - x) * total_schedule
    return 100 * (total_actual - total_schedule) / pool_denom

def compare_pooled_vs_individual(plants, quantile_forecasts,
                                  schedules, dsm_engine):
    individual_total = sum(
        dsm_engine.compute_expected_penalty(qf, sch, p.avc_mw, ...)
        for p, qf, sch in zip(plants, quantile_forecasts, schedules)
    )
    pooled_total = dsm_engine.compute_expected_penalty(
        pool_aggregate_forecast, sum(schedules), pool_avc_mw, ...
    )
    savings_pct = (individual_total - pooled_total) / individual_total * 100
    return {"individual_inr": individual_total,
            "pooled_inr": pooled_total,
            "savings_pct": savings_pct}
```

### 6.5 Schedule Optimiser (`modules/optimize/schedule_optimizer.py`)

```python
# For each 15-min block independently (no battery):
# Search schedule S ∈ [0, AvC] in steps of 0.1 MW
# Objective: MIN expected ₹ penalty across 19 quantile scenarios

def optimize_block_schedule(block_quantiles, avc_mw, dsm_engine, ncd, freq):
    candidates = np.arange(0, avc_mw + 0.1, 0.1)
    best_s, best_cost = None, float("inf")
    for s in candidates:
        cost = dsm_engine.compute_expected_penalty(block_quantiles, s, avc_mw, freq, ncd)
        if cost < best_cost:
            best_cost, best_s = cost, s
    return best_s, best_cost

def optimize_day_ahead(quantile_forecast_96blocks, avc_mw, dsm_engine, ncd, freq_scenario):
    schedules, costs = [], []
    for block_q in quantile_forecast_96blocks:
        s, c = optimize_block_schedule(block_q, avc_mw, dsm_engine, ncd, freq_scenario)
        schedules.append(s), costs.append(c)
    return schedules, costs
```

### 6.6 Battery LP (`modules/optimize/battery_lp.py`)

```python
# PuLP + CBC solver
# Decision variables: charge[t], discharge[t], soc[t]  for t in 0..95
# Objective: MIN sum(expected_DSM_penalty[t](schedule[t]))
# Constraints:
#   schedule[t] = gen_forecast[t] + discharge[t] - charge[t]
#   0 ≤ schedule[t] ≤ AvC
#   0 ≤ charge[t] ≤ max_charge_power
#   0 ≤ discharge[t] ≤ max_discharge_power
#   soc[t] = soc[t-1] + η_charge × charge[t] - (1/η_discharge) × discharge[t]
#   soc_min ≤ soc[t] ≤ soc_max
#   soc[0] = soc_initial
#   soc[95] ≥ soc_min  (end-of-day constraint)

# Battery parameters (configurable in plants.yaml):
#   capacity_mwh, max_charge_mw, max_discharge_mw,
#   efficiency_charge, efficiency_discharge, degradation_cost_inr_per_mwh
```

---

## 7. Phase 4 — React Dashboard + RAG Copilot

### 7.1 Dashboard Panels

| Panel | Data Source | Key Metric |
|---|---|---|
| **Gujarat Plant Map** | `GET /plants` | Live status indicator per plant |
| **Forecast Fan Chart** | `GET /forecast?plant_id&date` | P10/P50/P90 over 96 blocks |
| **96-Block ₹ Risk Heatmap** | `POST /dsm` | Expected ₹ penalty per block, colour-coded |
| **Submit-P50 vs Optimised ₹** | `POST /optimize` | Side-by-side ₹ bars showing savings |
| **2026→2031 Regulation Slider** | Re-calls `POST /dsm` with rule_year param | ₹ exposure under future rule sets |
| **Pooling What-If Toggle** | `POST /pooling` | Individual vs pooled ₹ (show 30–65% saving) |
| **Grid Action Cards** | `POST /optimize` | Battery / curtailment / reserve with ₹ impact |
| **RAG Copilot Panel** | `POST /rag/query` | Chat with cited CERC clauses |

### 7.2 Forecast Fan Chart Spec

```jsx
// ForecastFanChart.jsx using Recharts
// X-axis: 96 blocks (0:15 IST → 24:00 IST)
// Y-axis: MW
// Layers (bottom to top):
//   - Shaded area: P10–P90 (light blue)
//   - Shaded area: P25–P75 (medium blue)
//   - Line: P50 (dark blue, bold)
//   - Line: Declared schedule (orange dashed)
//   - Line: Previous day actual (grey, for context)
//   - Markers: blocks where schedule outside P10–P90 band (red dots)
```

### 7.3 RAG Copilot Architecture

**Offline (Colab Notebook 10 — build index):**
```
CERC_DSM_2024.pdf + CERC_DSM_2026_amendment.pdf + IEGC_2023.pdf
         ↓
PyMuPDF: extract text with page numbers
         ↓
Clause-aware chunker:
  - Split on regulation clause patterns (e.g. "Regulation 5", "Clause 4.2")
  - Chunk metadata: {doc, section, clause, page, date, source_url}
  - Max chunk size: 512 tokens with 50-token overlap
         ↓
bge-m3 embeddings (multilingual, 1024-dim)
         ↓
pgvector storage in RDS (regulation_chunks table)
BM25 index in-memory (rank_bm25 library)
```

**Live (query handling):**
```
User query: "Why was Block 52 penalised ₹18,000?"
         ↓
bge-m3 query embedding
         ↓
Hybrid retrieval:
  - Dense: pgvector cosine similarity top-20
  - Sparse: BM25 keyword top-20
  - Merge + deduplicate → 40 candidates
         ↓
bge-reranker → top-5 chunks
         ↓
Check LLM response cache (hit? return cached)
         ↓
Cache miss → LiteLLM
  Primary:  Groq Llama 3.3 70B (~30 RPM / org)
  Fallback: Gemini Flash (on rate limit / error)
         ↓
Prompt structure:
  SYSTEM: "You explain DSM penalties using the context below.
           The ₹ figure {penalty_inr} and deviation {dev_pct}%
           are computed by our engine — do not change them.
           Always cite the clause and page number."
  USER: {query}
  CONTEXT: {top-5 retrieved chunks}
  ENGINE_RESULT: {dsm_engine output for this block}
         ↓
Answer: plain language + CERC clause + page + source link
```

### 7.4 Frontend Tech Stack

```
Framework:      React 18 + Vite
Charting:       Recharts (fan chart, bars) + react-leaflet (plant map)
Styling:        Tailwind CSS
API client:     Axios
State:          React Query (server state) + Zustand (UI state)
Heatmap:        Custom D3 heatmap for 96-block ₹ risk grid
Build output:   Static files → S3 bucket (served via CloudFront)
```

---

## 8. Phase 5 — Cloud Deployment & CI/CD

### 8.1 AWS Architecture

```
Users (HTTPS)
     ↓
Amazon CloudFront (CDN + ACM certificate)
     ├── default /* → S3 (React static build, private bucket + OAC)
     └── /api/*   → Application Load Balancer (HTTPS, ACM)
                        ↓
                   EC2 t3.large (8 GB, Docker)
                   Security Group: ALB-only inbound
                        ├── FastAPI (port 8000)
                        └── Nginx (port 80, proxy)
                             ↓
                        RDS PostgreSQL + pgvector
                        (Security Group: EC2-only inbound)
                        S3 data bucket
                        (raw/ processed/ models/ regulations/ mlflow-artifacts/)
```

### 8.2 EventBridge Daily Pipeline

```
Trigger: EventBridge Scheduler → cron(30 2 * * ? *)   # 02:30 UTC = 08:00 IST
         (Before RLDC schedule submission cutoff)
         ↓ calls POST /pipeline/run (API key authenticated)

Pipeline steps (logged to job_runs table):
  1. Fetch Open-Meteo Forecast API for all plants
  2. Validate + feature engineering (15-min blocks)
  3. Load champion model from S3 → forecast P05–P95 all plants
  4. DSM engine: expected ₹ per block per plant (using today's rule_date → X)
  5. Optimise schedule (grid search + battery LP if battery configured)
  6. Curtailment / backup flags + pooling analysis
  7. Store all results → RDS (forecasts, schedules, dsm_results, actions, pooling_results)
  8. Pre-generate LLM briefings for each plant → cache
  9. Dashboard reads precomputed results (no blocking compute on user requests)
```

### 8.3 Secrets & Configuration

```
SSM Parameter Store (SecureString):
  /renewable/groq_api_key
  /renewable/gemini_api_key
  /renewable/db_password
  /renewable/pipeline_api_key

Repo (versioned, NOT secrets):
  config/dsm_rules_2024.yaml
  config/dsm_rules_2026.yaml
  config/dsm_rules_2031.yaml
  config/plants.yaml

.env.example (committed, never .env itself):
  DATABASE_URL=postgresql://user:password@localhost:5432/renewable
  GROQ_API_KEY=your_key_here
  GEMINI_API_KEY=your_key_here
  PIPELINE_API_KEY=your_key_here
  DSM_RULE_CONFIG=config/dsm_rules_2026.yaml
  S3_BUCKET_DATA=your-data-bucket
  S3_BUCKET_MODELS=your-models-bucket
```

### 8.4 CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml  — triggers on every push
steps:
  1. ruff check . --select E,F,W    # lint
  2. pytest tests/ -v --tb=short    # unit tests
  3. docker build -t app .          # build image
  4. trivy image app                # security scan
  5. OIDC → AWS → ECR push         # tag + push image

# .github/workflows/deploy.yml  — triggers on merge to main
steps:
  1. Pull new image tag
  2. SSM Run Command → EC2:
       docker compose pull
       docker compose up -d --no-deps backend
       curl localhost:8000/health || docker compose rollback
  3. Invalidate CloudFront cache (frontend)
  4. Notify Slack/Discord on success/failure
```

---

## 9. Database Schema

```sql
-- Plants
CREATE TABLE plants (
  id          VARCHAR PRIMARY KEY,   -- e.g. GJ_SOLAR_A
  name        TEXT,
  type        VARCHAR,               -- solar | wind
  lat         FLOAT, lon FLOAT,
  avc_mw      FLOAT,
  pool_id     VARCHAR,
  metadata    JSONB                  -- tilt, azimuth, hub_height, etc.
);

-- Weather Forecasts (as-issued)
CREATE TABLE weather_forecasts (
  id          BIGSERIAL PRIMARY KEY,
  plant_id    VARCHAR REFERENCES plants(id),
  issue_time  TIMESTAMPTZ,           -- when forecast was issued (UTC)
  valid_time  TIMESTAMPTZ,           -- 15-min block start (UTC)
  ghi_w_m2   FLOAT, dni_w_m2 FLOAT, dhi_w_m2 FLOAT,
  wind_10m   FLOAT, wind_80m FLOAT, wind_120m FLOAT,
  temp_c     FLOAT, humidity_pct FLOAT,
  clear_sky_ghi FLOAT, clear_sky_index FLOAT,
  source     VARCHAR                 -- openmeteo_forecast | era5
);

-- Probabilistic Forecasts (model output)
CREATE TABLE forecasts (
  id          BIGSERIAL PRIMARY KEY,
  plant_id    VARCHAR REFERENCES plants(id),
  run_id      UUID,                  -- links to job_runs
  valid_time  TIMESTAMPTZ,
  block_no    INT,                   -- 1–96 (or 1–288)
  model_name  VARCHAR,               -- lgbm | chronos | persistence | ensemble
  p05 FLOAT, p10 FLOAT, p25 FLOAT, p50 FLOAT,
  p75 FLOAT, p90 FLOAT, p95 FLOAT,
  calibrated  BOOLEAN DEFAULT FALSE
);

-- Day-Ahead Schedules
CREATE TABLE schedules (
  id          BIGSERIAL PRIMARY KEY,
  plant_id    VARCHAR REFERENCES plants(id),
  schedule_date DATE,
  block_no    INT,
  schedule_type VARCHAR,             -- naive_p50 | optimised | submitted
  schedule_mw FLOAT,
  run_id      UUID
);

-- DSM Results (per block, per scenario)
CREATE TABLE dsm_results (
  id             BIGSERIAL PRIMARY KEY,
  plant_id       VARCHAR REFERENCES plants(id),
  run_id         UUID,
  valid_time     TIMESTAMPTZ,
  block_no       INT,
  schedule_mw    FLOAT,
  expected_penalty_inr FLOAT,        -- probability-weighted across quantiles
  p50_penalty_inr FLOAT,             -- penalty if P50 actualised
  optimised_penalty_inr FLOAT,
  rule_version   VARCHAR,            -- CERC_DSM_2024 | CERC_DSM_2026 | ...
  x_value        FLOAT,
  savings_inr    FLOAT               -- expected_penalty - optimised_penalty
);

-- Battery / Action Outputs
CREATE TABLE actions (
  id              BIGSERIAL PRIMARY KEY,
  plant_id        VARCHAR REFERENCES plants(id),
  run_id          UUID,
  valid_time      TIMESTAMPTZ,
  block_no        INT,
  action_type     VARCHAR,           -- battery_charge | battery_discharge | curtailment | reserve_flag
  action_mw       FLOAT,
  soc_mwh         FLOAT,
  reason          TEXT
);

-- Pooling Results
CREATE TABLE pooling_results (
  id                   BIGSERIAL PRIMARY KEY,
  pool_id              VARCHAR,
  run_id               UUID,
  schedule_date        DATE,
  individual_penalty_inr FLOAT,
  pooled_penalty_inr   FLOAT,
  savings_pct          FLOAT
);

-- RAG Regulation Chunks (with pgvector)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE regulation_chunks (
  id          BIGSERIAL PRIMARY KEY,
  doc_name    VARCHAR,
  section     VARCHAR,
  clause      VARCHAR,
  page_no     INT,
  source_url  TEXT,
  effective_date DATE,
  chunk_text  TEXT,
  embedding   VECTOR(1024)           -- bge-m3 output
);
CREATE INDEX ON regulation_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Backtest Metrics
CREATE TABLE backtest_metrics (
  id          BIGSERIAL PRIMARY KEY,
  plant_id    VARCHAR,
  model_name  VARCHAR,
  run_date    DATE,
  horizon_h   INT,                   -- 6, 12, 24, 48, 72
  mae_mw      FLOAT,
  rmse_mw     FLOAT,
  pinball_p10 FLOAT,
  pinball_p50 FLOAT,
  pinball_p90 FLOAT,
  crps        FLOAT,
  picp_80     FLOAT,
  skill_vs_persistence FLOAT
);

-- Daily Job Runs
CREATE TABLE job_runs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_time    TIMESTAMPTZ DEFAULT now(),
  status      VARCHAR,               -- running | success | failed
  plants_processed INT,
  error_msg   TEXT,
  duration_s  FLOAT
);
```

---

## 10. API Contract

```
GET  /plants                      → List all plants with metadata
GET  /plants/{plant_id}           → Single plant detail

GET  /forecast?plant_id=&date=    → P10/P50/P90 per 96 blocks for a date
                                    Response: {blocks: [{block, time, p10, p50, p90}]}

POST /dsm                         → Compute expected ₹ penalty for a given schedule
     Body: {plant_id, date, schedule_mw_per_block[96], rule_year}
     Response: {blocks: [{block, expected_inr, p50_inr}], total_expected_inr}

POST /optimize                    → Find min-₹ schedule + battery dispatch
     Body: {plant_id, date, rule_year, battery_config?}
     Response: {optimised_schedule[96], battery_dispatch[96],
                naive_total_inr, optimised_total_inr, savings_inr, savings_pct,
                action_cards: [{type, block, mw, reason, inr_impact}]}

POST /pooling                     → What-if pooling simulator
     Body: {pool_id, date, rule_year}
     Response: {individual_inr, pooled_inr, savings_pct,
                per_plant_allocation: [{plant_id, allocated_inr}]}

POST /rag/query                   → RAG copilot query
     Body: {question, plant_id?, block_no?, context?}
     Response: {answer, citations: [{clause, page, doc, url}],
                engine_values: {penalty_inr, deviation_pct}}

GET  /dashboard/{plant_id}        → Precomputed dashboard data for today
     Response: {forecast, dsm_results, actions, pooling, briefing}

POST /pipeline/run                → Trigger daily pipeline (API-key protected)
     Response: {run_id, status}
```

---

## 11. Config & Secret Management

```
Principle: DSM rules live in versioned YAML in the repo.
           Secrets live in SSM Parameter Store, never in code.
           Business config lives in settings.yaml.

config/settings.yaml:
  app:
    name: "Renewable Forecasting Platform"
    version: "1.0.0"
    timezone: "Asia/Kolkata"
  forecast:
    default_horizon_blocks: 96       # 24h
    max_horizon_blocks: 288          # 72h
    quantile_levels: [0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,
                      0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95]
    model_champion_path: "s3://bucket/models/champion/"
  dsm:
    default_rule_config: "config/dsm_rules_2026.yaml"
    ncd_default_inr_per_mwh: 450
  rag:
    top_k_retrieve: 5
    cache_ttl_seconds: 3600
    primary_llm: "groq/llama-3.3-70b-versatile"
    fallback_llm: "gemini/gemini-1.5-flash"
  pipeline:
    schedule_cron: "30 2 * * *"      # 08:00 IST
```

---

## 12. Evaluation & Validation Plan

### 12.1 Three-Level Evaluation Framework

**Level 1 — Point Accuracy**

| Metric | Formula | Target |
|---|---|---|
| MAE | mean(|actual − P50|) | < 10% of AvC |
| nMAE | MAE / AvC | < 0.10 |
| RMSE | sqrt(mean((actual − P50)²)) | < 15% of AvC |
| Skill vs Persistence | 1 − MAE_model / MAE_persistence | > 0.20 |

**Level 2 — Uncertainty Quality**

| Metric | Formula | Target |
|---|---|---|
| Pinball Loss | mean(q × max(y−ŷ,0) + (1−q) × max(ŷ−y,0)) per quantile | Lower than persistence |
| CRPS | integral of (F(y) − 1{y≤ŷ})² dy | Lower than persistence |
| PICP (80%) | P(P10 ≤ actual ≤ P90) | 0.78–0.82 |
| PICP (90%) | P(P05 ≤ actual ≤ P95) | 0.88–0.92 |
| Reliability Diagram | Empirical coverage at each stated quantile | On the diagonal |

**Level 3 — Decision Quality**

| Metric | What it measures |
|---|---|
| Expected ₹ naive vs optimised | Does optimisation actually reduce ₹ cost? |
| Backtested action replay | Would recommended actions have helped historically? |
| Pooling savings | Does pooling model reproduce the 30–65% Prayas finding? |

### 12.2 Rolling-Origin Backtest Protocol

```
Dataset: 2+ months of 15-min generation + weather
Split: last 14 days = test, all prior = training
Walk-forward: train on days 1–N, forecast day N+1, advance by 1 day
Evaluate per horizon band: 0–6h, 6–12h, 12–24h, 24–48h, 48–72h
Report: separate metrics per horizon band (6-hour forecast ≠ 66-hour forecast)
No peeking: assert no feature uses any data from after the forecast issue time
```

### 12.3 DSM Engine Validation

```
Input: elinaparajuli/DSM-calculation-2024 SLDC data (March 2024, 2,976 blocks)
Method: feed same Actual/Schedule/Freq into our engine (buyer-side mode)
        compare output vs published `Calculated_deviation.csv`
Target: match within ₹1 per block on all 2,976 rows
Note: our engine adds seller-side X-trajectory on top — validate separately
      using synthetic test cases from CERC regulation text
```

---

## 13. Disclosures

These must appear in the report AND in the UI:

| Item | Statement |
|---|---|
| Demo generation | Physics-simulated from real Open-Meteo weather; validated on 34 days of real Indian inverter data (Kaggle dataset) |
| Wind power curve | Fitted on European turbines (CARE Wind Farm A, CC BY-SA 4.0); extrapolated to Gujarat sites |
| 15-min weather | Interpolated from hourly; native 15-min not available outside Europe/North America |
| DSM rules | Follow 2026 CERC order, which is under legal challenge in Delhi High Court; old vs new rules are both available via config slider |
| AvC | Generation > AvC flagged but not clipped in actuals; schedule constrained to [0, AvC] |
| LLM role | ML predicts generation uncertainty; DSM engine prices it; optimiser decides; LLM only explains. LLM never produces ₹ values |
| Backup | Platform **flags** backup/reserve requirements; does NOT actuate generation assets |
| Validation scope | Validated on limited real Indian data; multi-season validation is future work |

---

## 14. Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Weather data | Open-Meteo (no key, CC BY 4.0) | Free, as-issued historical + live forecast |
| Physics | pvlib (Python) | Established solar/PV model library |
| Wind | scipy curve_fit + NumPy power law | Fit sigmoid on CARE data, extrapolate to hub height |
| ML forecasting | LightGBM (quantile objective) | Native probabilistic output, fast on CPU |
| Foundation model | Chronos-2-small (28M params) | Pre-trained time-series, zero-shot on new plants |
| Feature engineering | pandas + pvlib + NumPy | Standard scientific Python stack |
| Optimisation | PuLP + CBC solver | Open-source MIP for 96-block battery LP |
| Backend | FastAPI + Python 3.11 | Typed API, async, same language as ML |
| Database | PostgreSQL 15 + pgvector | One store for operational + vector similarity |
| Migrations | Alembic | Schema versioning |
| RAG retrieval | bge-m3 (embeddings) + rank_bm25 + bge-reranker | Hybrid dense+sparse, multilingual |
| LLM | Groq Llama 3.3 70B → Gemini Flash (fallback) | Via LiteLLM provider-agnostic gateway |
| Agent framework | LangGraph | RAG copilot orchestration |
| Frontend | React 18 + Vite + Tailwind + Recharts + Leaflet | Fast, interactive, mobile-aware |
| Containerisation | Docker + docker-compose | Single command local setup |
| Cloud | AWS (EC2, S3, RDS, CloudFront, ALB, ECR, EventBridge, CloudWatch, SSM) | Production-grade, scheduled automation |
| CI/CD | GitHub Actions + OIDC (no long-lived AWS keys) | Secure, zero-touch deploy |
| Experiment tracking | MLflow (artifact store = S3) | Model versioning, metrics history |
| Offline training | Google Colab T4 (free) | GPU for Chronos-2 fine-tuning, bge-m3 embedding |

---

## 15. Delivery Timeline

| Day | Deliverable |
|---|---|
| **Day 1** | Repo scaffold, config YAMLs, docker-compose, FastAPI skeleton, DB schema, `.env.example` |
| **Day 2** | Data ingestion (Open-Meteo live + historical, NASA POWER), quality layer, 15-min pipeline |
| **Day 3** | Physics layer (pvlib solar + wind curve), feature engineering, persistence baseline |
| **Day 4** | LightGBM quantile model, calibration, Colab backtesting notebook |
| **Day 5** | Chronos-2 zero-shot + fine-tuning, model selection/ensemble |
| **Day 6** | DSM engine (full CERC 2024/2026 seller rules + YAML config), unit tests |
| **Day 7** | Schedule optimiser (grid search), battery LP (PuLP), pooling simulator |
| **Day 8** | FastAPI routes fully wired, daily pipeline orchestration |
| **Day 9** | React dashboard: plant map, fan chart, ₹ heatmap, action cards, regulation slider |
| **Day 10** | RAG copilot: PDF ingestion, bge-m3 embedding, hybrid retrieval, LiteLLM |
| **Day 11** | AWS deployment: EC2, RDS, S3, CloudFront, EventBridge, SSM |
| **Day 12** | CI/CD (GitHub Actions), CloudWatch alarms, integration testing |
| **Day 13** | Evaluation report (Colab notebook 11), backtest metrics, ₹ savings chart |
| **Day 14** | Polish, disclosures in UI, final demo, submission |

---

> [!NOTE]
> **The unique space we occupy:** No existing repo combines probabilistic forecast → rupee penalty (CERC 2026 seller rules) → optimised schedule → battery dispatch → pooling analysis → explainable regulatory citation. Each piece exists separately. We are the only team that chains all of them.

> [!IMPORTANT]
> **The legal disclosure to include in UI:** *"DSM parameters follow the 2026 CERC order, which is under legal challenge in the Delhi High Court. Both pre-2026 and post-2026 rules are available via the regulation year slider. All ₹ values are computed by our deterministic DSM engine, not by the AI language model."*
