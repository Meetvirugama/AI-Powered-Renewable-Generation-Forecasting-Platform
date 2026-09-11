# 🌞⚡ AI-Powered Renewable Generation Forecasting Platform
### DSM-Aware Decision & Scheduling Platform — Project Understanding

---

## 🎯 The One-Line Mission

> **Predict → Quantify Risk → Price in ₹ → Optimise → Act → Explain with Citations**

The platform doesn't stop at forecasting renewable generation — it propagates uncertainty into **operational and financial decision-making** and recommends the action that minimises expected grid imbalance cost.

---

## 🧠 The Core Insight (Why This Project Is Different)

Most forecasting tools give a **point forecast** (a single line on a graph). This project asks: *"So what?"*

| Operator's real question | What a point forecast tells them |
|---|---|
| How much reserve should I hold? | ❌ Nothing — no downside risk info |
| Which schedule should I declare? | ❌ Nothing — all nearby schedules look equal |
| What will it cost me if I'm wrong? | ❌ Nothing — MW error ≠ ₹ cost |
| Should I charge the battery now? | ❌ Nothing — depends on spread, not mean |

**The fix:** Produce a *distribution* (P10/P50/P90), price it in ₹ via the DSM engine, then *optimise* the action.

---

## 🏗️ The 6-Layer Architecture

```
Raw Inputs
    ↓
1. DATA INGESTION          → Open-Meteo weather, historical generation, site params, CERC regulations
    ↓
2. DATA QUALITY + FEATURES → Timestamp normalisation, 15-min resampling, solar geometry, lag features
    ↓
3. HYBRID FORECASTING      → pvlib (physics) + LightGBM (quantile ML) + Chronos-2 + Persistence baseline
    ↓
4. DECISION INTELLIGENCE   → DSM engine (₹ per scenario) + Schedule Optimiser + Battery LP (PuLP/CBC)
    ↓
5. RECOMMENDED ACTIONS     → Battery dispatch plan, Curtailment advisory, Reserve/Backup flags
    ↓
6. DELIVERY + EXPLANATION  → React Dashboard + RAG Regulatory Copilot (LangGraph + Groq/Gemini)
```

> [!IMPORTANT]
> **The critical boundary:** Everything numerical (₹, MW, deviations) happens in Layer 4 via deterministic code. The LLM in Layer 6 **only explains** — it never computes a number.

---

## 📊 ML Forecasting Stack

| Model | Why chosen |
|---|---|
| **LightGBM (quantile)** | Native quantile objective → P05–P95 directly, no post-hoc assumption |
| **Chronos-2-small** | Pretrained time-series foundation model, strong on limited history sites |
| **Persistence baseline** | The floor — any model that can't beat it has proven nothing |
| **pvlib** | Physics-based solar geometry, clear-sky irradiance, cell-temp derating |

**Output:** Full P05–P95 quantile set (19 levels), displayed as P10/P50/P90 per 15-min block across 96–288 blocks (24–72 hours).

---

## 💰 The DSM Engine (The Differentiator)

In India, deviation from scheduled generation is **financially settled** via CERC's Deviation Settlement Mechanism (DSM).

```
Deviation % = 100 × (Actual − Schedule) / (X·AvC + (1−X)·Schedule)
     ↓
₹ per scenario (19 quantiles × block)
     ↓
Expected ₹ penalty (probability-weighted)
     ↓
Optimiser: MIN expected ₹ → best schedule + battery dispatch
```

The DSM parameters (X trajectory, tolerance bands, charge rates) live in a **versioned YAML config** — so regulatory changes don't require model retraining.

---

## ⚡ Decision & Optimisation

| Scenario | Platform Response |
|---|---|
| **Over-generation** (actual > schedule) | Battery charge → schedule revision → curtailment (last resort) |
| **Under-generation** (actual < schedule) | Battery discharge → reserve flag → backup notification |
| **Battery optimisation** | 96-block LP (PuLP + CBC solver) with SOC, power, efficiency constraints |
| **Portfolio pooling** | Aggregate plants → errors partially cancel → lower net DSM exposure |

---

## 🤖 RAG Regulatory Copilot

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

## 🖥️ Frontend Dashboard (React)

| Panel | What it shows |
|---|---|
| Gujarat Plant Map | Site locations with live status |
| Forecast Fan Chart | P10/P50/P90 bands |
| 96-Block ₹ Risk Heatmap | Financial exposure per time block |
| Submit-P50 vs Optimised ₹ | Savings from optimisation |
| 2026→2031 Regulation Slider | Re-runs DSM engine with future rule sets |
| Pooling What-If Toggle | Individual vs pooled settlement comparison |
| Grid Action Cards | Recommended actions with ₹ impact |
| RAG Copilot Panel | Ask questions, get cited answers |

---

## ☁️ Cloud Architecture (AWS)

```
Users → CloudFront (CDN + HTTPS)
           ├── S3 (React static build)
           └── ALB → EC2 t3.large (Docker)
                         ├── FastAPI Modular Monolith
                         │     /plants /forecast /dsm /optimize /pooling /rag /pipeline/run
                         ├── RDS PostgreSQL + pgvector
                         └── S3 (data bucket: raw/ processed/ models/ regulations/)

EventBridge → Daily pipeline trigger (before schedule submission cutoff)
SSM Parameter Store → Secrets (Groq key, Gemini key, DB creds)
CloudWatch → Logs, alarms, LLM usage counters
ECR → Docker images (CI/CD via GitHub Actions + OIDC)
```

---

## 🔄 Daily Pipeline (Automated)

1. Fetch Open-Meteo Forecast API (next 24–72h weather)
2. Validate + feature engineering
3. Forecast P05–P95 for all plants
4. DSM engine: ₹ per scenario
5. Optimise schedule + battery LP
6. Curtailment / backup flags + pooling
7. Store results → RDS
8. Pre-generate + cache LLM briefings
9. Dashboard reads precomputed results

---

## 🗂️ Data Sources

| Source | Purpose | Mode |
|---|---|---|
| Open-Meteo Historical API | Training weather (as-issued) | Offline |
| ERA5 / NASA POWER | Reference "actual" weather | Offline |
| Kaggle Indian Solar Plant | 34 days, 15-min real inverter data (validation) | Offline |
| Open-Meteo Forecast API | Live next 24–72h weather | Live |
| CERC/IEGC regulations (PDFs) | RAG corpus | Offline build |
| pvlib simulation | Demo-plant MW generation | Both |

---

## 📐 Evaluation Metrics

| Level | Metric | Purpose |
|---|---|---|
| Point accuracy | MAE, RMSE (normalised) | Per horizon band |
| Point accuracy | Skill vs persistence | Does the model earn its complexity? |
| Uncertainty quality | Pinball loss | Individual quantile sharpness |
| Uncertainty quality | CRPS | Full distribution accuracy |
| Uncertainty quality | PICP | Are stated confidence intervals honest? |
| Uncertainty quality | Reliability diagram | Calibration across probability range |
| Decision quality | Expected ₹ baseline vs optimised | Does uncertainty → ₹ → decision actually help? |

---

## 📋 5-Phase Delivery Roadmap

| Phase | Focus |
|---|---|
| **Phase 1** | Data pipeline: weather + generation ingestion, quality layer, persistence baseline |
| **Phase 2** | Forecasting: pvlib + LightGBM + Chronos-2 + backtesting + P10/P50/P90 output |
| **Phase 3** | Decision layer: DSM engine + schedule optimiser + battery LP (PuLP/CBC) |
| **Phase 4** | Interface: React dashboard, what-if simulator, SHAP, calibration views, RAG copilot |
| **Phase 5** | Deployment: AWS, EventBridge, CI/CD, CloudWatch, validation report |

---

## 🔑 Key Design Principles

| Principle | Implication |
|---|---|
| **Decision-first** | Every component exists to improve a decision |
| **Uncertainty is first-class** | Quantiles propagate through ALL layers |
| **Money is computed, never generated** | LLM never produces ₹ values |
| **Physics before parameters** | pvlib estimate feeds the ML model as a feature |
| **Honest claims only** | Limitations stated upfront (not discovered in demo) |

---

## ⚠️ Known Limitations (Stated Honestly)

- Demo generation is physics-simulated (not long-term real plant data)
- Validation on limited Indian dataset (34 days); multi-season validation is future work
- Wind power curve fitted on European turbines (CARE Wind Farm A)
- 15-min weather interpolated from hourly outside Europe/North America
- Platform **flags** backup needs — does NOT actuate backup generation
- Net-load forecasting not present (no demand data in problem statement)
- Marginal emissions: reports displacement, not true marginal grid emissions

