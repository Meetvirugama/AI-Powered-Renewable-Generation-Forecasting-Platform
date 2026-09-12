# GridMind — System Architecture Diagram

> ASCII component diagram — four major zones, all connections labelled.
> Read top → bottom: data flows from live feeds through the core engine to the UI.

---

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                           🌐  EXTERNAL DATA SOURCES                                 ║
║                                                                                      ║
║   ┌─────────────────┐    ┌─────────────────┐    ┌──────────────────────────────┐    ║
║   │  Open-Meteo API │    │  NASA POWER API │    │  CERC / IEGC Regulation PDFs │    ║
║   │  72h Weather    │    │  Solar Irrad.   │    │  2024 · 2026 · 2031 gazettes │    ║
║   └────────┬────────┘    └────────┬────────┘    └──────────────┬───────────────┘    ║
╚════════════╪════════════════════════╪════════════════════════════╪════════════════════╝
             │ httpx async            │ httpx async                │ PDF ingest
             ▼                        ▼                            ▼
╔════════════════════════════════════════════╗   ╔════════════════════════════════════╗
║           🤖  AI / ML ENGINE               ║   ║        🧠  RAG COPILOT             ║
║  ┌─────────────────────────────────────┐  ║   ║  ┌──────────────────────────────┐  ║
║  │  Data Ingestion Pipeline            │  ║   ║  │  bge-m3 Embedder             │  ║
║  │  • Quality Validator                │  ║   ║  │  (1024-dim dense vectors)    │  ║
║  │  • 15-min Grid Resampler (IST)      │  ║   ║  ├──────────────────────────────┤  ║
║  │  • AvC clipping · GHI zeroing       │  ║   ║  │  BM25 Sparse Index           │  ║
║  └──────────────┬──────────────────────┘  ║   ║  (rank-bm25 over 2k chunks)   │  ║
║                 │                          ║   ║  ├──────────────────────────────┤  ║
║  ┌──────────────▼──────────────────────┐  ║   ║  │  RRF Hybrid Retriever        │  ║
║  │  Feature Builder (61 features)      │  ║   ║  │  (dense + sparse fusion)     │  ║
║  │  • Cyclical time · Solar angles     │  ║   ║  ├──────────────────────────────┤  ║
║  │  • Weather lags · Wind shear        │  ║   ║  │  Financial Guardrail         │  ║
║  └──────────────┬──────────────────────┘  ║   ║  │  (strips LLM rupee output)   │  ║
║                 │                          ║   ║  ├──────────────────────────────┤  ║
║  ┌──────────────▼──────────────────────┐  ║   ║  │  LiteLLM Gateway             │  ║
║  │  LightGBM Quantile Boosters          │  ║   ║  │  Groq Llama 3.3 70B /        │  ║
║  │  12 models: 24h / 48h / 72h         │  ║   ║  │  Gemini 1.5 Flash            │  ║
║  │  P10 · P50 · P90 per horizon        │  ║   ║  └──────────────┬───────────────┘  ║
║  └──────────────┬──────────────────────┘  ║   ╚═════════════════╪══════════════════╝
║                 │ P05–P95 fan             ║                     │
║  ┌──────────────▼──────────────────────┐  ║                     │ answer + citations
╚══╡  → /forecast blocks[96]             ╞══╝                     │
   └──────────────┬──────────────────────┘                        │
                  │                                                │
                  ▼                                                ▼
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                         ⚡  BACKEND  (FastAPI · port 8000)                           ║
║                                                                                      ║
║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║  │  REST API Routers                                                            │   ║
║  │                                                                              │   ║
║  │  GET  /plants          GET  /plants/{id}      GET  /forecast?plant_id&date  │   ║
║  │  POST /dsm             POST /optimize          POST /pooling                 │   ║
║  │  GET  /dashboard/{id}  POST /rag/query         POST /pipeline/run            │   ║
║  │  GET  /health          GET  /rag/health                                      │   ║
║  └──────────┬───────────────────────┬──────────────────────┬────────────────────┘   ║
║             │                       │                      │                         ║
║  ┌──────────▼──────────┐ ┌──────────▼──────────┐ ┌────────▼────────────────────┐   ║
║  │  DSM Engine          │ │  Optimiser           │ │  Portfolio Pooling          │   ║
║  │  CERC X-Trajectory   │ │  Grid Search         │ │  Multi-plant netting        │   ║
║  │  Frequency tiers     │ │  (min expected ₹)    │ │  Pro-rata allocation        │   ║
║  │  NCD + seller rules  │ │  + Battery LP        │ │  ~27% reduction measured   │   ║
║  │  2024/2026/2031 YAML │ │  (PuLP/CBC 96-block) │ │  Correlation: 0.70         │   ║
║  └──────────┬──────────┘ └──────────┬──────────┘ └────────┬────────────────────┘   ║
║             │                       │                      │                         ║
║             └───────────────────────┴──────────────────────┘                         ║
║                                     │                                                ║
║                      Deterministic ₹ penalty figures                                 ║
╚═════════════════════════════════════╪════════════════════════════════════════════════╝
                                      │
                    ┌─────────────────┼──────────────────┐
                    │ reads/writes    │                  │ reads/writes
                    ▼                 ▼                  ▼
╔═══════════════════════════════════════════════════════════════════════════════════════╗
║                              🗄️  STORAGE                                             ║
║                                                                                       ║
║  ┌──────────────────────────────────┐   ┌────────────────────────────────────────┐  ║
║  │  PostgreSQL 15 (relational)      │   │  pgvector (HNSW cosine, 1024-dim)      │  ║
║  │                                  │   │                                        │  ║
║  │  • plants                        │   │  • regulation_chunks                   │  ║
║  │  • weather_forecasts             │   │    (CERC/IEGC PDFs split into          │  ║
║  │  • forecasts                     │   │     chunks, embedded by bge-m3)        │  ║
║  │  • schedules                     │   │                                        │  ║
║  │  • dsm_results                   │   │  BM25 Index (in-memory at boot)        │  ║
║  │  • actions                       │   │  • built from same regulation_chunks   │  ║
║  │  • pooling_results               │   │  • ~1s build, 2k chunks                │  ║
║  │  • job_runs                      │   │                                        │  ║
║  └──────────────────────────────────┘   └────────────────────────────────────────┘  ║
║                                                                                       ║
║  ┌──────────────────────────────────┐   ┌────────────────────────────────────────┐  ║
║  │  config/ (YAML, static)          │   │  prediction_bundle/ (file system)      │  ║
║  │  • dsm_rules_2024.yaml           │   │  • 12 LightGBM .pkl boosters           │  ║
║  │  • dsm_rules_2026.yaml           │   │    24h / 48h / 72h × P10/P50/P90      │  ║
║  │  • dsm_rules_2031.yaml           │   │    (currently rejected by physics      │  ║
║  │  • plants.yaml (seed data)       │   │     gate — mock engine active)         │  ║
║  └──────────────────────────────────┘   └────────────────────────────────────────┘  ║
╚═══════════════════════════════════════════════════════════════════════════════════════╝
                                      ▲
                    JSON over HTTP (axios · AbortController)
                                      │
╔═══════════════════════════════════════════════════════════════════════════════════════╗
║                         🖥️  FRONTEND  (React 19 · Vite 6 · port 5173)               ║
║                                                                                       ║
║  ┌────────────────────────────────────────────────────────────────────────────────┐  ║
║  │  App Shell                                                                     │  ║
║  │  AppLayout ─── AppSidebar (Overview · Forecast · Risk · Actions · DSM Copilot) │  ║
║  │             └── AppHeader (mobile hamburger)                                   │  ║
║  │                                                                                │  ║
║  │  DashboardShell ── PlantSelector (GJ_SOLAR_A/B, GJ_WIND_C, GJ_SOLAR_D)       │  ║
║  │                 └── RuleYearControl (2024 / 2026 / 2031)                      │  ║
║  └──────────────────────────────┬─────────────────────────────────────────────────┘  ║
║                                 │  DashboardContext (plantId + ruleYear)             ║
║       ┌─────────────────────────┼──────────────────────────┐                        ║
║       ▼                         ▼                          ▼                        ║
║  ┌────────────┐       ┌─────────────────────┐       ┌──────────────────────────┐   ║
║  │  Overview  │       │  Forecast page       │       │  Risk page               │   ║
║  │            │       │                     │       │                          │   ║
║  │ StatTile×4 │       │  ForecastFanChart   │       │  RiskHeatmap             │   ║
║  │ BriefingCard│       │  P05–P95 bands      │       │  96 blocks · pen ramp    │   ║
║  │ PlantMap   │       │  P50 median line     │       │                          │   ║
║  └────────────┘       │  Optimised schedule  │       │  ScheduleComparison      │   ║
║                       │  (dashed stepline)   │       │  Naive vs optimised bars │   ║
║                       └─────────────────────┘       └──────────────────────────┘   ║
║                                                                                       ║
║  ┌─────────────────────────────┐          ┌──────────────────────────────────────┐  ║
║  │  Actions page               │          │  Copilot page                        │  ║
║  │                             │          │                                      │  ║
║  │  ActionCards                │          │  RAGCopilot                          │  ║
║  │  • curtailment              │          │  • Chat input                        │  ║
║  │  • reserve_flag             │          │  • Answer panel                      │  ║
║  │  (type · block · MW · ₹)   │          │  • Citation badges (clause/doc/page) │  ║
║  │                             │          │  • Guardrail status display          │  ║
║  │  PoolingToggle              │          │                                      │  ║
║  │  Individual ↔ Pooled totals │          │  POST /rag/query                     │  ║
║  │  Per-plant allocation table │          │  context = live DSM engine values    │  ║
║  └─────────────────────────────┘          └──────────────────────────────────────┘  ║
║                                                                                       ║
║  ─────────────────────────  API Layer  ──────────────────────────────────────────── ║
║                                                                                       ║
║  api/client.ts → api/endpoints.ts → hooks/use*.ts → pages & components              ║
║                                                                                       ║
║  useDashboard   usePlants    useForecast   useDSM      useOptimize                   ║
║  usePooling     useRAG       useHealth     useSidebar  useModal  useGoBack           ║
║                                                                                       ║
║  VITE_USE_MOCKS=true → mocks/ (dashboard.json · optimize.json · plants.json · rag)  ║
╚═══════════════════════════════════════════════════════════════════════════════════════╝
```

---

## Connection index

| Arrow | From | To | Protocol / data |
|---|---|---|---|
| Weather fetch | Open-Meteo + NASA POWER | ML Ingestion Pipeline | `httpx` async HTTP |
| PDF ingest | CERC regulation PDFs | bge-m3 Embedder + BM25 | file read → chunk → embed |
| Forecast output | LightGBM boosters | Backend `/forecast` | Python function call |
| DSM pricing | Backend DSM Engine | `/dsm`, `/dashboard` | Pydantic response |
| Optimiser output | Grid search + Battery LP | `/optimize`, `/dashboard` | Pydantic response |
| Pooling savings | Portfolio Pooling Engine | `/pooling`, `/dashboard` | Pydantic response |
| RAG answer | LiteLLM → Guardrail | `/rag/query` response | JSON + citations array |
| DB reads/writes | All backend engines | PostgreSQL 15 | SQLAlchemy 2.0 ORM |
| Vector search | RAG Retriever | pgvector (HNSW) | cosine similarity |
| Sparse search | RAG Retriever | BM25 in-memory index | term frequency |
| Config load | DSM Engine | `config/*.yaml` | YAML file read at startup |
| Model load | Forecast Engine | `prediction_bundle/*.pkl` | joblib deserialise |
| Frontend → API | React hooks (axios) | FastAPI routers | JSON over HTTP, AbortController |
| Plant select | `PlantMap` / `PlantSelector` | `DashboardContext` | React state |
| Rule year change | `RuleYearControl` | `useDSM` re-fetch | POST /dsm with new `rule_year` |
| Copilot context | Live DSM engine values | `POST /rag/query .context` | JSON object |

---

## Seed data — Gujarat portfolio

```
GJ_SOLAR_A  50 MW  solar  lat 23.0  lon 72.5  pool GJ_POOL_1
GJ_SOLAR_B  75 MW  solar  lat 23.5  lon 71.5  pool GJ_POOL_1
GJ_WIND_C   40 MW  wind   lat 22.8  lon 70.2  pool GJ_POOL_1
GJ_SOLAR_D  30 MW  solar  lat 23.8  lon 72.0  pool GJ_POOL_2
```

Map centre: `23.2°N, 71.0°E`

---

## Engine status flags (from `GET /health`)

```
{
  "forecast":  "mock"       ← LightGBM models trained but rejected by physics gate
  "optimizer": "production" ← real 23–28% measured reduction
  "pooling":   "production" ← real ~27% measured reduction
  "rag":       "mock"       ← production bge-m3 ready; corpus empty until PDFs land
}
```

`serving_synthetic_data: ["forecast"]` is published in every `/health` response so the
UI can render the honesty badge. Sprint 10 wires this to the header.

---

## One-day data flow (96 blocks = 15-minute IST intervals)

```
00:00 IST  ──▶  Weather forecast arrives (Open-Meteo 72h pull, async)
               │
               ▼
           Validator + Resampler → 96 blocks aligned to IST Block 1..96
               │
               ▼
           Feature Builder (61 features per block)
               │
               ▼
           LightGBM × 12 boosters → P10/P50/P90 per horizon
               │
               ▼
           Quantile sorter → P05 P10 P25 P50 P75 P90 P95 (monotone)
               │
               ▼ stored in DB (forecasts table)
               │
           DSM Engine reads forecast + schedule
               │  applies X-trajectory (2026 rule: X=0.72)
               │  applies frequency tier (50Hz nominal → band ±0.15Hz)
               ▼
           Expected penalty ₹ per block (BlockDSMResult × 96)
               │
               ├──▶ Grid Search Optimiser → min-expected-₹ schedule
               │         └──▶ Battery LP (PuLP/CBC) → BESS charge/discharge
               │
               ├──▶ Portfolio Pooling → netting across GJ_POOL_1
               │
               ├──▶ Action Cards (curtailment / reserve_flag) emitted
               │
               └──▶ Dashboard assembled → GET /dashboard/{plant_id}
                           │
                           ▼
                    React frontend renders:
                    ForecastFanChart  RiskHeatmap  ScheduleComparison
                    StatTile×4        BriefingCard  ActionCards  PlantMap
                    (RAGCopilot queries independently on user question)
```

---

*Owners: Meet Virugama (ML) · Gaurav Rathod (Backend) · Shane Christian (Frontend) · Madhav Thesiya (Infra/RAG)*  
*Built for Hackout 2026.*
