# AI-Powered Renewable Generation Forecasting Platform
### DSM-Aware Decision & Scheduling Platform — Project Understanding

---

## Mission

> **Predict → Quantify Risk → Price in ₹ → Optimise → Act → Explain with Citations**

The platform doesn't stop at forecasting renewable generation — it propagates uncertainty into **operational and financial decision-making** and recommends the action that minimises expected grid imbalance cost.

---

## Why This Is Different From a Forecast Tool

Most forecasting tools give a **point forecast** (a single line on a graph). This project asks: *"So what?"*

| Operator's real question | What a point forecast tells them |
|---|---|
| How much reserve should I hold? | Nothing — no downside risk info |
| Which schedule should I declare? | Nothing — all nearby schedules look equal |
| What will it cost me if I'm wrong? | Nothing — MW error ≠ ₹ cost |
| Should I charge the battery now? | Nothing — depends on spread, not mean |

**The fix:** Produce a *distribution* (P05–P95), price it in ₹ via the DSM engine, then *optimise* the action.

---

## The 6-Layer Architecture

```
Raw Inputs
    ↓
1. DATA INGESTION          → Open-Meteo weather, historical generation, site params, CERC regulations
    ↓
2. DATA QUALITY + FEATURES → Timestamp normalisation, 15-min resampling, solar geometry, lag features
    ↓
3. HYBRID FORECASTING      → pvlib (physics) + LightGBM (quantile ML) + Persistence baseline
    ↓
4. DECISION INTELLIGENCE   → DSM engine (₹ per scenario) + Schedule Optimiser + Battery LP (PuLP/CBC)
    ↓
5. RECOMMENDED ACTIONS     → Battery dispatch plan, Curtailment advisory, Reserve/Backup flags
    ↓
6. DELIVERY + EXPLANATION  → React Dashboard + RAG Regulatory Copilot (Groq/Gemini)
```

**Critical boundary:** Everything numerical (₹, MW, deviations) happens in Layer 4 via deterministic code. The LLM in Layer 6 **only explains** — it never computes a number. The `/health` endpoint exposes `serving_synthetic_data` so this claim is verifiable at runtime.

---

## ML Forecasting Stack

| Model | Why chosen |
|---|---|
| **LightGBM (quantile)** | Native quantile objective → P05–P95 directly, no post-hoc assumption |
| **Persistence baseline** | The floor — any model that can't beat it has proven nothing |
| **pvlib** | Physics-based solar geometry, clear-sky irradiance, cell-temp derating |

> **Chronos-2:** Mentioned in the original plan; explicitly descoped. See `docs/roadmap.md`.

**Output:** P05–P95 quantile set, displayed per 15-min block across 96 blocks (24 hours).

---

## The DSM Engine (The Differentiator)

In India, deviation from scheduled generation is **financially settled** via CERC's Deviation Settlement Mechanism (DSM).

```
Deviation % = 100 × (Actual − Schedule) / (X·AvC + (1−X)·Schedule)
     ↓
₹ per scenario (7 quantiles × 96 blocks)
     ↓
Expected ₹ penalty (probability-weighted)
     ↓
Optimiser: MIN expected ₹ → best schedule + battery dispatch
```

The DSM parameters (X trajectory, tolerance bands, charge rates) live in a **versioned YAML config** — regulatory changes don't require model retraining. Three rule years shipped: 2024, 2026, 2031.

---

## Decision & Optimisation

| Scenario | Platform Response |
|---|---|
| **Over-generation** (actual > schedule) | Battery charge → schedule revision → curtailment (last resort) |
| **Under-generation** (actual < schedule) | Battery discharge → reserve flag → backup notification |
| **Battery optimisation** | 96-block LP (PuLP + CBC solver) with SOC, power, efficiency constraints |
| **Portfolio pooling** | Aggregate plants → errors partially cancel → lower net DSM exposure |

---

## RAG Regulatory Copilot

**"Why was Block 52 penalised?"**

```
Query
  → bge-m3 embedding
  → Hybrid retrieval (BM25 + vector search in pgvector)
  → bge-reranker
  → Retrieved CERC/IEGC clauses + DSM engine result (₹, MW)
  → LiteLLM → Groq Llama 3.3 70B (fallback: Gemini Flash)
  → Answer with clause + page + source link (never a hallucinated number)
```

**Corpus:** CERC DSM Regulations 2024 + 2026 amendment, IEGC 2023, CERC orders.

---

## Frontend Dashboard (React 19 · Vite 6 · Tailwind v4)

| Panel | What it shows |
|---|---|
| Gujarat Plant Map | 4 seeded plants, click to select |
| Forecast Fan Chart | P05–P95 bands, P50 median, optimised schedule overlay |
| 96-Block Risk Heatmap | ₹ penalty exposure per time block |
| Schedule Comparison | Submit-P50 vs optimised, with savings tile |
| Regulation Slider | 2024 / 2026 / 2031 re-runs DSM engine live |
| Pooling Toggle | Individual vs pooled settlement comparison |
| Action Cards | Recommended curtailment/reserve flags with ₹ impact |
| RAG Copilot Panel | Ask questions, get cited answers |

---

## Cloud Architecture (AWS)

```
Users → CloudFront (CDN + HTTPS)
           ├── S3 (React static build)
           └── ALB → EC2 t3.large (Docker)
                         ├── FastAPI Modular Monolith
                         │     /plants /forecast /dsm /optimize /pooling /rag /pipeline/run
                         ├── RDS PostgreSQL 15 + pgvector
                         └── S3 (data bucket)

EventBridge → Daily pipeline trigger (08:00 IST — before SLDC cutoff)
SSM Parameter Store → Secrets (Groq key, Gemini key, DB creds)
CloudWatch → Logs, alarms, LLM usage counters
ECR → Docker images (CI/CD via GitHub Actions + OIDC)
```

---

## Daily Pipeline (Automated, 9 Steps)

1. Fetch Open-Meteo Forecast API (next 72h weather)
2. Validate + feature engineering
3. Forecast P05–P95 for all plants
4. DSM engine: ₹ per scenario
5. Optimise schedule + battery LP
6. Curtailment / backup flags + pooling
7. Store results → RDS
8. Pre-generate + cache LLM briefings
9. Dashboard reads precomputed results

---

## Data Sources

| Source | Purpose | Mode |
|---|---|---|
| Open-Meteo Historical API | Training weather (as-issued) | Offline |
| ERA5 / NASA POWER | Reference "actual" weather | Offline |
| Kaggle Indian Solar Plant | 34 days, 15-min real inverter data (validation) | Offline |
| Open-Meteo Forecast API | Live next 24–72h weather | Live |
| CERC/IEGC regulations (PDFs) | RAG corpus | Offline build |
| pvlib simulation | Demo-plant MW generation | Both |

---

## Key Design Principles

| Principle | Implication |
|---|---|
| **Decision-first** | Every component exists to improve a decision |
| **Uncertainty is first-class** | Quantiles propagate through ALL layers |
| **Money is computed, never generated** | LLM never produces ₹ values |
| **Physics before parameters** | pvlib estimate feeds the ML model as a feature |
| **Honest claims only** | Limitations stated upfront — not discovered in demo |

---

## Known Limitations (Stated Honestly)

- Demo generation is physics-simulated (not long-term real plant data)
- Trained LightGBM models currently fail the physics plausibility gate (see `docs/model_integration.md`) — forecasts are synthetic pending retraining
- Validation on a single 34-day Indian dataset; multi-season validation is future work
- Wind power curve fitted on European turbines
- Platform **flags** backup needs — does NOT actuate backup generation
- Net-load forecasting not present (no demand data)
