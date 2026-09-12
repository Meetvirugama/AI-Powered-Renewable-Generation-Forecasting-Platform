# Roadmap — what is left, and the order to do it in

**Audited against `main` @ PR #8 merged.** 167 tests passing, `ruff` clean.

Every "missing" below was verified against the tree, not inferred from the plan. Percentages are
scope-completion estimates, not confidence.

---

## Where the project actually stands

| Track | Owner | Built | Demo-ready |
|---|---|---|---|
| Backend / API / data | Member 2 | **97%** | ✅ yes |
| Infra / RAG copilot | Member 4 | **95%** | ⚠️ code yes, corpus empty |
| ML / forecasting | Member 1 | **55%** | ❌ models can't serve |
| Frontend | Member 3 | **5%** | ❌ stock Vite template |

**Overall: ~65% built, ~45% demo-ready.**

Against the six-step value chain in the README:

| Step | State |
|---|---|
| 1. Ingest weather | ✅ real (Open-Meteo → validator → `weather_forecasts`) |
| 2. Forecast P05–P95 | ⚠️ mock (models trained but rejected by physics gate) |
| 3. Price in ₹ (CERC DSM) | ✅ real |
| 4. Optimise schedule | ✅ real — 23–28% reduction, measured |
| 5. Flag grid actions | ✅ real (derived from optimiser output) |
| 6. Explain with citations | ⚠️ engine works, no corpus loaded |

---

## 🔴 Blockers — fix before presenting

### B1. Pooling makes penalties *worse*, not better

`compute_pooling_benefit` aggregates quantiles assuming **perfect correlation** between plants —
its own comment says so. That assumption removes the entire diversification benefit, which is the
only reason pooling helps at all.

Measured against the 4 configured plants:

```
GJ_POOL_1 (3 plants)   individual ₹78,930/day → pooled ₹87,999/day   = -11.5%
README claims                                                          +30-65%
```

Pooling only pays when deviations are *imperfectly* correlated — one plant over-injects while
another under-injects and they net out. Summing P05s assumes every plant hits its worst case at
the same instant, which is the opposite of diversification.

**Fix:** combine spreads by the variance-addition rule, `√(Σσ²)` rather than `Σσ`, with a
configurable correlation coefficient. ~1 hour.

**Risk if unfixed:** you state "30–65%" on stage, a judge asks to see it, the platform shows −11.5%.

### B2. Block numbering is UTC, but Indian scheduling blocks are IST

`resampler.py:33` computes `block_no` from UTC hours. CERC defines block 1 as 00:00–00:15 **IST**.
Verified offset: **22 blocks**.

Latent until the forecast models work — the mock ignores weather — but the ingestion pipeline is
live now, so weather sampled at dawn is already being labelled midnight.

**Fix:** shift to IST before computing `block_no`, plus a test asserting the resampler and
`feature_builder` agree. ~20 minutes.

---

## Remaining work by owner

### Member 1 — ML (~55%)

**Delivered and good:** the DSM engine (`engine.py`, `config_loader.py`, `pooling.py`) is the
strongest domain code in the repo — X-trajectory by date, frequency bands, seller-side rules,
YAML-driven for 2024/2026/2031. Plus 12 trained LightGBM boosters.

**Missing modules** (6 of 7 planned):

| File | Purpose | Needed for demo? |
|---|---|---|
| `features.py` | feature engineering | **yes** — retraining + `feature_builder` |
| `physics.py` | pvlib solar + wind power curve | no |
| `persistence.py` | baseline for skill scores | for evidence |
| `calibration.py` | PICP, reliability diagrams | for evidence |
| `ensemble.py` | model selection | no |
| `chronos_model.py` | Chronos-2 wrapper | no — **drop it** |
| `battery_lp.py` | PuLP/CBC 96-block LP | no |

**Model retraining** — six changes, detailed in `docs/model_integration.md`:

1. Drop `DC_POWER`, `DAILY_YIELD`, `TOTAL_YIELD` (leak; `DC_POWER` alone is ~25% of gain)
2. Fix `PLANT_ID` — constant `none`, so models can't serve 4 plants
3. Predict in MW, or capacity factor (see below)
4. Constrain non-negative (raw min is −1.43)
5. Chronological splits — 373 test rows across all horizons implies one random split
6. Rebuild conformal calibration on a held-out window

> **Data limit, not an effort limit.** The dataset is 2,774 rows / **29.9 days** / **1 plant**
> (2020-05-16 → 2020-06-14, kW scale). Per-plant models for 4 Gujarat sites are impossible, and
> so is 5-fold rolling-origin CV.
>
> **Workaround:** train on **capacity factor** (`AC_POWER / capacity`, 0–1), then multiply by each
> plant's `avc_mw` at inference. Solves the 22× scale mismatch *and* the single-plant problem.
> Disclose it as "trained on a reference plant, applied via capacity-factor normalisation."

**Missing tests:** `test_physics.py`, `test_optimizer.py`
**Missing notebooks:** all 10 (`01`–`09`, `11`) — no backtest harness, no evaluation report
**Missing handoffs:** `features_schema.json` (→ M2), `quantile_forecast_output.csv` (→ M3)

### Member 2 — Backend (~97%)

Essentially done. All 11 endpoints, 10 tables + migrations, ingestion wired, `/pipeline/run`
async with 202, API-key auth enforced, zero TODO markers.

**Remaining:** B2 (block numbering) only.

### Member 3 — Frontend (~5%)

`frontend/` exists and deploys to Vercel, but `App.jsx` is the stock Vite counter demo.

**All 8 components missing:** `PlantMap`, `ForecastFanChart`, `RiskHeatmap`, `ScheduleComparison`,
`RegulationSlider`, `PoolingToggle`, `ActionCards`, `RAGCopilot`
**Also missing:** `Dashboard.jsx`, `PlantDetail.jsx`, `Backtest.jsx`, `api/client.js`, all hooks
**Dependencies not installed:** recharts, leaflet, tailwind, router, axios (only react + react-dom)

**Priority order if time is short:** `client.js` → `ForecastFanChart` → `RiskHeatmap` →
`RAGCopilot` → `PoolingToggle`. Skip the map, `PlantDetail`, `Backtest`, and role tabs.

### Member 4 — Infra + RAG (~95% code, ~60% operational)

Code complete and tested. Blocked on inputs, not engineering.

| Item | Blocker |
|---|---|
| Regulation PDFs | **human must download** from cercind.gov.in |
| `sources.json` URLs | 6 `FILL_ME` placeholders; every citation badge renders one |
| Groq API key | free at console.groq.com — required for a real copilot |
| AWS deploy | 0 repo secrets configured; `main` CI red at `Configure AWS credentials` |
| `generate_briefing()` wiring | deferred — needs a schema change, and the corpus is empty |

> **The 2.2 GB embedding model is optional.** BM25-only retrieval works — verified: real citations,
> rule-year filter, and the ₹ guardrail all function without it. The trade-off is vocabulary
> matching: *"what is the tolerance band for solar?"* retrieves fine, *"why was block 52
> penalised?"* returns nothing. Install `requirements-ml.txt` if bandwidth allows.

---

## Roadmap

### Phase 0 — Demo-critical (1–2 days)

Ordered by value per hour. Everything here is achievable in the window.

| # | Task | Owner | Time | Unblocks |
|---|---|---|---|---|
| 1 | **Fix pooling correlation (B1)** | M4 | 1h | Headline claim stops being negative |
| 2 | **Regulation PDFs + `sources.json`** | **human** | 1h | Copilot cites real CERC clauses |
| 3 | **Groq key → `.env`** | **human** | 5m | Copilot generates real answers |
| 4 | **Fix block numbering (B2)** | M4 | 20m | Weather aligns with IST blocks |
| 5 | **Frontend: 4 core components** | M3 | 1–2d | The only thing judges see |
| 6 | **Demo script + failover rehearsal** | all | 1h | Most teams lose here, not on tech |
| 7 | Deploy (or local fallback) | M4 | 2h | One URL |

**Do not attempt in Phase 0:** model retraining, Chronos-2, battery LP, notebooks.

### Phase 1 — Makes the ML real (3–5 days)

| # | Task | Time |
|---|---|---|
| 8 | `features.py` — canonical feature builder | 2h |
| 9 | Retrain on capacity factor, no leaking features | 4h |
| 10 | `persistence.py` + backtest notebook (08) | 4h |
| 11 | Flip `FORECAST_ENGINE_TYPE=production`, confirm physics gate passes | 30m |
| 12 | `quantile_forecast_output.csv` + `features_schema.json` | 30m |

### Phase 2 — Completes the plan (1–2 weeks)

`physics.py`, `calibration.py`, `ensemble.py`, `battery_lp.py`, notebooks 01–07/09/11,
`test_physics.py`, `test_optimizer.py`, Terraform apply, EventBridge unattended run,
`generate_briefing()` wired into the pipeline.

### Explicitly descoped

Chronos-2 (`chronos_model.py`, notebooks 06/07) — in the README tech stack, absent from the repo,
and not needed for any demo claim. **Either build it or remove it from the README** before a judge
asks.

---

## What you can honestly claim today

✅ CERC 2026 seller-side DSM pricing with X-trajectory — real, tested
✅ Min-₹ schedule optimisation — **23–28% reduction**, measured against your own engine
✅ Live weather ingestion — Open-Meteo → validation → 15-min blocks → DB
✅ Action cards — each carrying a real rupee delta
✅ A copilot that **structurally cannot** invent a ₹ figure — guardrail enforced post-generation
✅ Engine transparency — `/health` reports `serving_synthetic_data`

⚠️ Forecasts are synthetic (disclosed by the API itself)
⚠️ Copilot cites nothing until the PDFs land
❌ Pooling — **do not quote 30–65% until B1 is fixed**

### The strongest honest framing

Don't present this as a forecasting project — everyone forecasts. Present the **decision layer**:
pricing deviation in rupees under real CERC rules, optimising the schedule against it, and
explaining it with citations that cannot fabricate money.

And demo the rejection:

> "We connected our trained LightGBM models and the engine refused them — 22× scale mismatch, and
> they predicted solar generation at midnight. We caught it before it reached the ₹ engine.
> `/health` will tell you exactly which parts of this dashboard are synthetic."

That is a stronger story than a model accuracy number, and most teams will not have it.
