# Roadmap — what is left, and the order to do it in

**Audited against `main` @ PR #11 merged.** 183 tests passing, `ruff` clean, 0 CRLF-corrupted models.

Every "missing" below was verified against the tree, not inferred from the plan. Percentages are
scope-completion estimates, not confidence.

---

## Where the project actually stands

| Track | Owner | Built | Demo-ready | Change |
|---|---|---|---|---|
| Backend / API / data | Gaurav Rathod | **97%** | ✅ yes | — |
| Frontend | Shane Christian | **85%** | ✅ yes | **↑ from 5%** |
| Infra / RAG copilot | Madhav Thesiya | **95%** | ⚠️ corpus empty | — |
| ML / forecasting | Meet Virugama | **58%** | ❌ models rejected | ↑ docs added |

**Overall: ~84% built, ~70% demo-ready.** Up from 65% / 45% at the last audit.

The frontend landing is the single biggest change — it was the critical-path blocker and it is now
substantially done.

Against the six-step value chain in the README:

| Step | State |
|---|---|
| 1. Ingest weather | ✅ real (Open-Meteo → validator → `weather_forecasts`) |
| 2. Forecast P05–P95 | ⚠️ mock (models trained but rejected by the physics gate) |
| 3. Price in ₹ (CERC DSM) | ✅ real |
| 4. Optimise schedule | ✅ real — **23–28% reduction**, measured |
| 5. Flag grid actions | ✅ real (derived from optimiser output) |
| 6. Explain with citations | ⚠️ engine works, no corpus loaded |
| — Portfolio pooling | ✅ real — **~27%**, measured (was −11.5% before PR #10) |

---

## 🔴 Remaining blocker

### B2. Block numbering is UTC, but Indian scheduling blocks are IST

`resampler.py:33` computes `block_no` from UTC hours. CERC defines block 1 as 00:00–00:15 **IST**.
Verified offset: **22 blocks**.

Weather sampled at dawn is currently labelled midnight. Latent while forecasts are mock (the mock
ignores weather), but the ingestion pipeline is live, so the `weather_forecasts` rows being written
today already carry the wrong block association.

**Fix:** shift to IST before computing `block_no`, plus a test asserting the resampler and
`feature_builder` agree. ~20 minutes.

> **B1 (pooling correlation) — FIXED** in PR #10. Was −11.5%, now +26.8% at a conservative 0.70
> correlation. README claims corrected from "30–65%" to the measured "~27%".

---

## Remaining work by owner

### Shane Christian — Frontend (~85%) ✅ *was the critical path, no longer is*

Real React + TypeScript application, wired to live endpoints via `axios`.

**Delivered:** all 8 planned components (`ForecastFanChart`, `RiskHeatmap`, `ScheduleComparison`,
`ActionCards`, `RAGCopilot`, `PlantMap`, `PoolingToggle`, plus `StatTile`/`BriefingCard`),
5 pages, 11 hooks covering every API, `api/client.ts`, layout shell, context, Tailwind, routing,
ApexCharts, Leaflet.

**Endpoints wired:** `/plants`, `/plants/{id}`, `/forecast`, `/dsm`, `/optimize`, `/pooling`,
`/rag/query`, `/rag/health`, `/health`.

**Remaining:**

| Item | Effort | Note |
|---|---|---|
| Surface `serving_synthetic_data` in the UI | 30m | `useHealth.ts` fetches `/health` but ignores `engines` and `serving_synthetic_data`. **This is the honesty badge** — see the pitch note below. |
| `/dashboard/{plant_id}` not used | — | The UI composes from individual endpoints instead. Fine, but the precomputed route exists and is cheaper. |
| Loading / error states, mobile | 2–3h | Polish |
| `.env.production` with the deployed API URL | 5m | Needed once deployed |

### Gaurav Rathod — Backend (~97%)

Essentially done. 11 endpoints, 10 tables + migrations, ingestion wired, `/pipeline/run` async
with 202, API-key auth enforced, zero TODO markers.

**Remaining:** B2 (block numbering) only.

### Madhav Thesiya — Infra + RAG (~95% code, ~60% operational)

Code complete and tested. Blocked on inputs, not engineering.

| Item | Blocker |
|---|---|
| Regulation PDFs | **human must download** from cercind.gov.in |
| `sources.json` URLs | 6 `FILL_ME` placeholders; every citation badge renders one |
| Groq API key | free at console.groq.com — required for a real copilot |
| AWS deploy | 0 repo secrets; `main` CI red at `Configure AWS credentials` |
| `generate_briefing()` wiring | deferred — needs a schema change, and the corpus is empty |

> **The 2.2 GB embedding model is optional.** BM25-only retrieval works — verified: real citations,
> rule-year filter, and the ₹ guardrail all function without it. The trade-off is vocabulary
> matching: *"what is the tolerance band for solar?"* retrieves fine, *"why was block 52
> penalised?"* returns nothing.

### Meet Virugama — ML (~58%)

**Delivered and good:** the DSM engine (`engine.py`, `config_loader.py`) — X-trajectory by date,
frequency bands, seller-side rules, YAML-driven for 2024/2026/2031. 12 trained LightGBM boosters.
`docs/ml_pipeline.md` (902 lines) added in PR #12.

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
2. Fix `PLANT_ID` — constant `none`, so models cannot serve 4 plants
3. Predict in MW, or capacity factor (see below)
4. Constrain non-negative (raw min is −1.43)
5. Chronological splits — 373 test rows across all horizons implies one random split
6. Rebuild conformal calibration on a held-out window

> **Data limit, not an effort limit.** 2,774 rows / **29.9 days** / **1 plant**
> (2020-05-16 → 2020-06-14, kW scale). Per-plant models for 4 Gujarat sites are impossible, as is
> 5-fold rolling-origin CV.
>
> **Workaround:** train on **capacity factor** (`AC_POWER / capacity`, 0–1), multiply by each
> plant's `avc_mw` at inference. Solves the scale mismatch *and* the single-plant problem.
> Disclose as "trained on a reference plant, applied via capacity-factor normalisation."

**Missing tests:** `test_physics.py`, `test_optimizer.py`
**Missing notebooks:** all 10 (`01`–`09`, `11`) — no backtest harness, no evaluation report
**Missing handoffs:** `features_schema.json` (→ M2), `quantile_forecast_output.csv` (→ M3)

---

## Roadmap

### Phase 0 — Demo-critical (remaining: ~4 hours of work)

| # | Task | Owner | Time | Status |
|---|---|---|---|---|
| ~~1~~ | ~~Fix pooling correlation~~ | Madhav | — | ✅ PR #10 |
| ~~5~~ | ~~Frontend core components~~ | Shane | — | ✅ PR #11 |
| 2 | **Regulation PDFs + `sources.json`** | **human** | 1h | ⬜ |
| 3 | **Groq key → `.env`** | **human** | 5m | ⬜ |
| 4 | Fix block numbering (B2) | Madhav | 20m | ⬜ |
| 6 | Surface `serving_synthetic_data` in UI | Shane | 30m | ✅ PR #13 |
| 7 | Demo script + failover rehearsal | all | 1h | ⬜ |
| 8 | Deploy, or rehearse the local fallback | Madhav | 2h | ⬜ |

**Do not attempt in Phase 0:** model retraining, Chronos-2, battery LP, notebooks.

### Phase 1 — Makes the ML real (3–5 days)

| # | Task | Time |
|---|---|---|
| 9 | `features.py` — canonical feature builder | 2h |
| 10 | Retrain on capacity factor, no leaking features | 4h |
| 11 | `persistence.py` + backtest notebook (08) | 4h |
| 12 | Flip `FORECAST_ENGINE_TYPE=production`, confirm the physics gate passes | 30m |
| 13 | `quantile_forecast_output.csv` + `features_schema.json` | 30m |

### Phase 2 — Completes the plan (1–2 weeks)

`physics.py`, `calibration.py`, `ensemble.py`, `battery_lp.py`, notebooks 01–07/09/11,
`test_physics.py`, `test_optimizer.py`, Terraform apply, EventBridge unattended run,
`generate_briefing()` wired into the pipeline, `/dashboard/{plant_id}` adopted by the UI.

### Explicitly descoped

Chronos-2 (`chronos_model.py`, notebooks 06/07) — in the README tech stack, absent from the repo,
not needed for any demo claim. **Either build it or remove it from the README** before a judge
greps for it.

---

## What you can honestly claim today

✅ CERC 2026 seller-side DSM pricing with X-trajectory — real, tested
✅ Min-₹ schedule optimisation — **23–28% reduction**, measured against your own engine
✅ Portfolio pooling — **~27% reduction**, measured, with the correlation assumption declared
✅ Live weather ingestion — Open-Meteo → validation → 15-min blocks → DB
✅ Action cards — each carrying a real rupee delta
✅ A copilot that **structurally cannot** invent a ₹ figure — guardrail enforced post-generation
✅ A real React dashboard wired to all of it
✅ Engine transparency — `/health` reports `serving_synthetic_data`

⚠️ Forecasts are synthetic (disclosed by the API itself)
⚠️ Copilot cites nothing until the PDFs land

### The strongest honest framing

Don't present this as a forecasting project — everyone forecasts. Present the **decision layer**:
pricing deviation in rupees under real CERC rules, optimising the schedule against it, netting it
across a portfolio, and explaining it with citations that cannot fabricate money.

And demo the rejection:

> "We connected our trained LightGBM models and the engine refused them — 22× scale mismatch, and
> they predicted solar generation at midnight. We caught it before it reached the ₹ engine.
> `/health` will tell you exactly which parts of this dashboard are synthetic."

That is a stronger story than a model accuracy number, and most teams will not have it. It only
works if the UI actually shows the badge — which is why item 6 above is worth its 30 minutes.
