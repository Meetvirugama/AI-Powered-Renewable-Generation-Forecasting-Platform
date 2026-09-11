# 👥 Team Division Plan
## AI-Powered Renewable Generation Forecasting Platform
### 4 Members · 1 ML Expert · Hackathon Sprint

---

## Team Roles at a Glance

| Member | Role | Core Skill Needed | Owns |
|---|---|---|---|
| **Member 1** | ML Engineer | Python + ML (the ML expert) | Forecasting engine, DSM engine, Colab notebooks, physics simulation |
| **Member 2** | Backend Engineer | Python + FastAPI + SQL | FastAPI API, database, data ingestion pipeline, daily pipeline |
| **Member 3** | Frontend Engineer | React + JavaScript | React dashboard, all UI components, charts, RAG chat panel |
| **Member 4** | Infra + RAG Engineer | Python + Cloud/Docker (learnable) | Docker, AWS deployment, CI/CD, RAG copilot, LLM integration |

---

## Member 1 — ML Engineer (The ML Expert) 🤖

**Why this person:** Only person who understands ML training, quantile regression, time-series forecasting, and physics models.

### Files Owned
```
colab_notebooks/
  01_data_acquisition.ipynb
  02_preprocessing.ipynb
  03_physics_simulation.ipynb
  04_feature_engineering.ipynb
  05_lgbm_quantile.ipynb
  06_chronos2_zeroshot.ipynb
  07_chronos2_finetune.ipynb
  08_backtesting.ipynb
  09_dsm_engine_test.ipynb
  11_evaluation_report.ipynb

backend/modules/forecast/
  physics.py         ← pvlib solar + wind power curve
  features.py        ← feature engineering
  lgbm_model.py      ← LightGBM quantile model
  chronos_model.py   ← Chronos-2 wrapper
  persistence.py     ← persistence baseline
  ensemble.py        ← model selection + ensemble
  calibration.py     ← PICP, reliability diagrams

backend/modules/dsm/
  engine.py          ← CERC DSM seller-side engine (core math)
  config_loader.py   ← YAML rule loader + X-trajectory resolver

backend/modules/optimize/
  schedule_optimizer.py  ← NumPy grid search
  battery_lp.py          ← PuLP + CBC battery LP

tests/
  test_dsm_engine.py
  test_physics.py
  test_optimizer.py
```

### Day-by-Day Tasks

| Day | Task |
|---|---|
| 1 | Set up Colab environment, clone NASA POWER data (Notebook 01), understand Open-Meteo API structure |
| 2 | Run preprocessing notebook (02): 15-min resampling, UTC/IST, feature set |
| 3 | Build pvlib solar simulation (03) + wind power curve fit on CARE data |
| 4 | Feature engineering notebook (04): lags, clear-sky index, seasonal features |
| 5 | Train LightGBM quantile model (05): P05–P95, SHAP attribution |
| 6 | Chronos-2 zero-shot (06) + fine-tuning experiment (07) |
| 7 | **DSM engine** (engine.py): CERC seller formula + X-trajectory + frequency bands + YAML config |
| 8 | Schedule optimiser + battery LP (PuLP) |
| 9 | Rolling-origin backtest harness (08): MAE, CRPS, PICP, pinball loss |
| 10 | DSM engine unit tests (09) + validation vs elinaparajuli SLDC data |
| 11 | Evaluation report notebook (11): ₹ savings, skill vs persistence |
| 12–14 | Help Member 2 wire model outputs into FastAPI endpoints, fix bugs |

### What Member 1 Hands Off to Others
- Saved model files (`.pkl`, `.pt`) → `S3/models/` (Member 4 uploads)
- Feature schema (`features_schema.json`) → Member 2 uses in data pipeline
- DSM engine `engine.py` → Member 2 imports in `/dsm` API route
- `quantile_forecast_output.csv` (sample) → Member 3 uses to build mock charts

---

## Member 2 — Backend Engineer 🔧

**Why this person:** Needs solid Python skills + SQL. Does NOT need to understand ML internals — just calls Member 1's module functions.

### Files Owned
```
backend/
  main.py                  ← FastAPI app entry point

backend/api/
  plants.py                ← GET /plants
  forecast.py              ← GET /forecast (calls Member 1's models)
  dsm.py                   ← POST /dsm (calls Member 1's engine)
  optimize.py              ← POST /optimize (calls Member 1's optimiser)
  pooling.py               ← POST /pooling
  dashboard.py             ← GET /dashboard
  pipeline.py              ← POST /pipeline/run

backend/modules/dsm/
  pooling.py               ← portfolio pooling logic

backend/modules/pipeline/
  daily.py                 ← 9-step daily orchestration pipeline

backend/data/
  ingestion/
    openmeteo.py           ← Open-Meteo live forecast API
    openmeteo_historical.py
    nasa_power.py
  quality/
    validator.py
    resampler.py
  simulation/              ← receives finished files from Member 1

backend/db/
  models.py                ← all SQLAlchemy ORM models (12 tables)
  session.py
  migrations/

backend/core/
  config.py
  logging.py
  security.py

config/
  plants.yaml
  settings.yaml
  dsm_rules_2024.yaml
  dsm_rules_2026.yaml
  dsm_rules_2031.yaml

requirements.txt
.env.example
```

### Day-by-Day Tasks

| Day | Task |
|---|---|
| 1 | Set up FastAPI project, install deps, write `main.py`, all route stubs, health check endpoint |
| 2 | DB models (SQLAlchemy, all 12 tables), Alembic migrations, test DB connection |
| 3 | Data ingestion: `openmeteo.py` (live forecast pull for all plants), `nasa_power.py` |
| 4 | Data quality: `validator.py` + `resampler.py` (15-min blocks, UTC/IST, AvC flag) |
| 5 | `plants.yaml` + config YAML (dsm rules 2024/2026/2031) + `settings.yaml` |
| 6 | Wire `GET /plants` and `GET /forecast` (mock data first, real model later) |
| 7 | Wire `POST /dsm` and `POST /optimize` (plug in Member 1's engine.py) |
| 8 | Wire `POST /pooling` + `GET /dashboard` (precomputed results from DB) |
| 9 | `daily.py` pipeline (9 steps, EventBridge trigger, logging to job_runs) |
| 10 | `POST /pipeline/run` endpoint + API key auth + full pipeline integration test |
| 11 | OpenAPI docs polish, error handling, logging, connect to Member 4's Docker setup |
| 12–14 | Bug fixes, integration with frontend (CORS, response format alignment with Member 3) |

### What Member 2 Hands Off to Others
- API base URL + all endpoint contracts → Member 3 (frontend client.js)
- `docker-compose.yml` backend service definition → Member 4
- DB connection string → Member 4 (SSM Parameter Store)

---

## Member 3 — Frontend Engineer ⚛️

**Why this person:** React + JavaScript. Does NOT need to know Python, ML, or AWS. Consumes the APIs Member 2 builds.

### Files Owned
```
frontend/
  public/
    index.html
  src/
    components/
      PlantMap.jsx           ← Gujarat plant locations (react-leaflet)
      ForecastFanChart.jsx   ← P10/P50/P90 band chart (Recharts)
      RiskHeatmap.jsx        ← 96-block ₹ heatmap (custom D3)
      ScheduleComparison.jsx ← Naive P50 vs Optimised ₹ bars
      RegulationSlider.jsx   ← 2026→2031 year slider (re-calls POST /dsm)
      PoolingToggle.jsx      ← Individual vs pooled ₹ what-if
      ActionCards.jsx        ← Battery / curtailment / reserve cards
      RAGCopilot.jsx         ← Chat panel with cited CERC answers
    pages/
      Dashboard.jsx
      PlantDetail.jsx
      Backtest.jsx
    hooks/
      useForecast.js
      useDSM.js
      useRAG.js
    api/
      client.js              ← Axios API client (base URL from .env)
    App.jsx
  package.json
  vite.config.js
```

### Day-by-Day Tasks

| Day | Task |
|---|---|
| 1 | React + Vite project setup, Tailwind CSS, router, `client.js` with mock base URL |
| 2 | `PlantMap.jsx`: Gujarat plant map with react-leaflet, hardcoded pins first |
| 3 | `ForecastFanChart.jsx`: P10/P50/P90 band using Recharts + mock JSON data (from Member 1's sample CSV) |
| 4 | `RiskHeatmap.jsx`: 96-block ₹ heatmap — green/yellow/red colour scale per block |
| 5 | `ScheduleComparison.jsx`: side-by-side bar chart (submit-P50 ₹ vs optimised ₹) |
| 6 | `ActionCards.jsx`: battery / curtailment / reserve flag cards with ₹ impact badges |
| 7 | `RegulationSlider.jsx`: year slider 2026→2031, on change re-calls POST /dsm, re-renders heatmap |
| 8 | `PoolingToggle.jsx`: toggle individual vs pooled ₹, show savings % |
| 9 | `RAGCopilot.jsx`: chat panel, send to POST /rag/query, render answer + citation badges |
| 10 | `Dashboard.jsx`: assemble all components, role-based tabs (Operator / Plant Owner / Trader) |
| 11 | `PlantDetail.jsx` + `Backtest.jsx` pages |
| 12 | Connect to real API (swap mock data for live `client.js` calls) |
| 13–14 | UI polish, mobile responsiveness, loading states, error boundaries |

### What Member 3 Needs from Others
- From **Member 2**: API base URL, endpoint paths, exact JSON response shapes
- From **Member 1**: sample forecast output CSV (to build mock data before API is ready)
- From **Member 4**: CloudFront URL (for final `.env.production` config)

---

## Member 4 — Infra + RAG Engineer ☁️

**Why this person:** Handles Docker, AWS, and the RAG copilot LLM integration. Python knowledge needed but not ML expertise. Most of this is learnable from documentation during the hackathon.

### Files Owned
```
backend/modules/rag/
  ingest.py          ← PyMuPDF PDF parsing + clause-aware chunking
  embed.py           ← bge-m3 embeddings
  retriever.py       ← BM25 + pgvector hybrid + bge-reranker
  cache.py           ← LLM response cache
  copilot.py         ← LangGraph agent + LiteLLM (Groq/Gemini)

backend/api/
  rag.py             ← POST /rag/query route (handed off to Member 2 to wire in)

colab_notebooks/
  10_rag_embed.ipynb ← Build pgvector index offline

regulations/
  CERC_DSM_Regulations_2024.pdf
  CERC_DSM_Amendment_2026.pdf
  IEGC_2023.pdf

Dockerfile
docker-compose.yml

infra/
  terraform/
    main.tf          ← VPC, EC2, RDS, S3, CloudFront, ALB, ECR, EventBridge
    variables.tf
    outputs.tf
  docker/
    nginx.conf

.github/
  workflows/
    ci.yml           ← lint + tests + docker build + image scan
    deploy.yml       ← OIDC → ECR push → SSM RunCommand → EC2 deploy
```

### Day-by-Day Tasks

| Day | Task |
|---|---|
| 1 | `Dockerfile` + `docker-compose.yml` (backend + postgres + pgvector), get entire stack running locally with `docker compose up` |
| 2 | Download 3 CERC/IEGC PDFs, set up Colab notebook 10: PyMuPDF text extraction, clause-aware chunking |
| 3 | bge-m3 embeddings (`embed.py`) in Colab, store chunks + embeddings in pgvector |
| 4 | BM25 index (`retriever.py`): rank_bm25 library, hybrid retrieval logic, bge-reranker reranking |
| 5 | Get Groq API key, test LiteLLM with Groq Llama 3.3 70B + Gemini Flash fallback |
| 6 | `copilot.py`: LangGraph agent — retrieval → cache check → LLM call → response with citations |
| 7 | `cache.py`: LLM response cache (in-memory dict or Redis, TTL 1h) |
| 8 | Wire `POST /rag/query` route with Member 2 (coordinate on request/response schema) |
| 9 | AWS setup: EC2 t3.large, RDS PostgreSQL + pgvector extension, S3 buckets, SSM Parameter Store with API keys |
| 10 | CloudFront + ALB + S3 (React build bucket), SSL certificate (ACM) |
| 11 | GitHub Actions CI pipeline (`ci.yml`): lint + tests + docker build + ECR push |
| 12 | GitHub Actions deploy pipeline (`deploy.yml`): OIDC → ECR → SSM RunCommand → health check |
| 13 | EventBridge scheduler trigger for daily pipeline, CloudWatch alarms |
| 14 | Final end-to-end deployment test, help debug any infra issues |

### What Member 4 Needs from Others
- From **Member 2**: `requirements.txt`, port numbers, API key env var names
- From **Member 1**: model files to upload to S3, bge-m3 embedding vectors for pgvector
- From **Member 3**: `npm run build` output folder for S3 upload

---

## 🔗 Dependency Map (Who Waits on Who)

```
Member 1 (ML)                Member 2 (Backend)           Member 3 (Frontend)          Member 4 (Infra/RAG)
     │                             │                             │                             │
Day 1: Colab setup           FastAPI skeleton             React + Vite setup           Docker compose up
     │                             │                             │                             │
Day 2: Data prep             DB models + migration        PlantMap mock                PDF chunking (Colab)
     │                             │                             │                             │
Day 3: Physics sim           Data ingestion               ForecastFanChart mock        bge-m3 embeddings
     │                             │                             │                             │
Day 4: Features              Data quality layer           RiskHeatmap mock             Hybrid retrieval
     │                             │                             │                             │
Day 5: LightGBM train        Config YAMLs                 ScheduleComparison           LiteLLM + Groq
     │                             │                             │                             │
Day 6: Chronos-2             Wire /plants, /forecast      ActionCards                  LangGraph copilot
     │                             │                             │                             │
Day 7: ←─── DSM engine.py ──────► Wire /dsm, /optimize   RegulationSlider             Cache + /rag/query
     │                             │                             │                             │
Day 8: Schedule + battery LP  Wire /pooling, /dashboard   PoolingToggle                AWS EC2 + RDS
     │                             │                             │                             │
Day 9: Backtest              Daily pipeline               RAGCopilot.jsx               CloudFront + ALB
     │                             │                             │                             │
Day 10: DSM unit tests       Pipeline /run endpoint       Dashboard.jsx assemble       GitHub Actions CI
     │                             │                             │                             │
Day 11: Eval report          API polish, CORS             Plant detail + Backtest      CD pipeline
     │                             │                             │                             │
Day 12: ←─── Help wire ML outputs into API ──────────────► Connect real API            EventBridge + CW
     │                             │                             │                             │
Day 13-14:                   Bug fixes                    UI polish                    Final deploy test
```

---

## 🚦 Critical Path (Don't Let These Block You)

| Risk | Mitigation |
|---|---|
| Member 3 blocked waiting for API | Use **mock JSON files** (from Member 1's sample CSV) — build all UI on mocks, swap to real API on Day 12 |
| Member 2 blocked waiting for ML models | Wire endpoints with **stub functions** that return hardcoded sample data first |
| Member 4 blocked on Groq rate limits | Implement response cache on Day 7, use Gemini Flash fallback immediately |
| DSM engine takes longer than expected | Member 1 gives Member 2 a **simple Python function** with the formula by Day 7 even if not fully tested |
| AWS credits run out | Build everything with **docker-compose locally** first; AWS deployment is last |

---

## 📋 Shared Responsibilities (Everyone)

| Task | Who |
|---|---|
| Write `README.md` (1 page each section) | Member 2 drafts, all review |
| Record 3-min demo video | Member 3 drives, all participate |
| Add disclosures to UI | Member 3 implements, Member 1 writes the text |
| Git commits (feature branches, PR to main) | Everyone — Member 4 sets up branch protection |
| Daily 15-min standup | All members, flag blockers early |

---

## 🗂️ What Each Member Needs to Know

### Member 1 (ML) — Pre-Requisites
- Python, pandas, NumPy
- LightGBM, scikit-learn
- `pip install chronos-forecasting` (Amazon Chronos)
- pvlib for solar physics
- PuLP for LP optimisation
- Google Colab GPU runtime

### Member 2 (Backend) — Pre-Requisites
- Python, FastAPI, SQLAlchemy
- PostgreSQL basics
- REST API design
- `pip install fastapi uvicorn sqlalchemy alembic psycopg2`
- NO ML knowledge needed — just call `from modules.forecast import lgbm_model`

### Member 3 (Frontend) — Pre-Requisites
- React, JavaScript/JSX
- Tailwind CSS
- Recharts (`npm install recharts`)
- react-leaflet (`npm install react-leaflet leaflet`)
- Axios (`npm install axios`)
- NO Python/ML/AWS knowledge needed

### Member 4 (Infra + RAG) — Pre-Requisites
- Docker + docker-compose (most important)
- Basic Python (for RAG scripts)
- AWS console basics (EC2, S3, RDS, CloudFront)
- LangGraph (`pip install langgraph litellm`)
- PyMuPDF (`pip install pymupdf`)
- Groq API key (free tier)
- NO deep ML knowledge needed
