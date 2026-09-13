# Roadmap — what is left, and the order to do it in

**Re-audited 13 September 2026** against `main` @ PR #36 plus PR #37 (`fix/audit-round-two`), and the running production API at
`https://57.159.24.68.nip.io`. 424 backend tests collected, `ruff` clean.

Live figures below were measured on production, which does not yet include PR #37. Its
quantile-weighting fix lowers expected-penalty figures site-wide, so re-measure after it deploys.

Every claim below was verified against the tree or against the live system, not inferred from the
plan. Percentages are scope-completion estimates, not confidence.

---

## Where the project actually stands

| Track | Owner | Built | Demo-ready | Change |
|---|---|---|---|---|
| Backend / API / data | Gaurav Rathod | **99%** | ✅ yes | ↑ B2 fixed |
| Frontend | Shane Christian | **85%** | ✅ yes | — |
| Infra / RAG copilot | Madhav Thesiya | **95%** | ✅ yes | ↑ corpus loaded, deployed |
| ML / forecasting | Meet Virugama | **80%** | ✅ yes | **↑ models retrained and serving** |

**Overall: ~92% built, ~90% demo-ready.**

The forecast going real is the change since the last audit. `/health` now reports
`serving_synthetic_data: []` — **nothing in the chain is mocked**.

Against the six-step value chain in the README:

| Step | State |
|---|---|
| 1. Ingest weather | ✅ real (Open-Meteo → validator → `weather_forecasts`) |
| 2. Forecast P05–P95 | ✅ **real** — LightGBM for solar at 24 / 48 / 72 h (+21.5% / +26.9% / +32.5% skill vs persistence), power curve for wind |
| 3. Price in ₹ (CERC DSM) | ✅ real |
| 4. Optimise schedule | ✅ real — saving varies with the day's weather; 15.5% for GJ_SOLAR_A on 13 Sept |
| 5. Flag grid actions | ✅ real (derived from optimiser output) |
| 6. Explain with citations | ✅ real — 179 chunks, 3 CERC documents, recall@5 = 0.73 |
| — Portfolio pooling | ✅ real — 25.6% for GJ_POOL_1 on 13 Sept, correlation assumption declared |

> Savings are measured per day against a calibrated band, so they move with the weather. Earlier
> audits recorded 30.2% (optimiser) and 34.5% (pooling) on other days. Quote the figure on screen.

---

## Remaining blockers

**None that stop a demo.** The two below limit answer quality, not availability.

### R1. The regulation corpus is thin and skewed

179 chunks from 3 documents, and 149 of them (83%) are the *Statement of Reasons* — the
Commission's commentary, not operative law. The principal regulations contribute 27 chunks, so
BM25 surfaces commentary for questions whose answer is in the regulation.

Measured: `recall@5 = 0.73` against a target of 0.70. Of the 4 misses, **3 expect documents that
are not in the corpus at all** — `IEGC`, and `CERC_DSM_Amendment_2026` (which does not exist as a
separate document; the 2026 X-trajectory is inside the 2024 principal regulations, so that
expectation in `tests/rag_eval_questions.json` is itself wrong and should be corrected).

**Fix:** add the IEGC PDF; correct the two eval questions. Requires a human to source the PDF.
This is the single biggest lever on RAG quality.

### R2. The indexed corpus predates the chunker fixes

PR #21 fixed two defects — 33% of chunks began mid-word, and 72% carried a page number whose page
does not contain their text. Those fixes are in the **chunker**; the rows already in Supabase were
built by the old one. Until `scripts/build_index.py` is re-run, the live corpus still has both
defects.

**Fix:** re-run the index build. ~2 minutes, reversible, rewrites the live corpus.

---

## Remaining work by owner

### Shane Christian — Frontend (~85%)

**Delivered:** all 8 planned components, 5 pages, 11 hooks, `api/client.ts`, layout shell,
context, Tailwind, routing, ApexCharts, Leaflet. Deployed on Vercel, pointing at the Azure API.

| Item | Effort | Note |
|---|---|---|
| Surface `serving_synthetic_data` in the UI | 30m | `useHealth.ts` fetches `/health` but ignores `engines` and `serving_synthetic_data`. Now that the list is **empty**, showing it is a claim in your favour rather than a disclaimer. |
| `/dashboard/{plant_id}` not used | — | The UI composes from individual endpoints. Fine, but the precomputed route is one request instead of five. |
| Loading / error states, mobile | 2–3h | Polish |

> The UI reads block times from `block_no`, not from `ist_time`. Worth knowing: `ist_time` is a
> bare `HH:MM` from the mock engine and a full ISO-8601 string from the production engine. Nothing
> renders it today, so the inconsistency is harmless — but do not start rendering it without
> normalising first.

### Gaurav Rathod — Backend (~99%)

11 endpoints, 10 tables + migrations, ingestion wired, `/pipeline/run` async with 202, API-key
auth enforced, zero TODO markers.

**B2 (IST block numbering) — FIXED.** `resampler.py` derives `block_no` from the IST wall clock
and the function carries the reasoning.

**Remaining:** nothing demo-critical.

### Madhav Thesiya — Infra + RAG (~95%)

Deployed and operational. Azure VM, systemd, Caddy, Let's Encrypt via `nip.io`, GitHub Actions
CI/CD with host-key pinning, health gate and rollback.

| Item | State |
|---|---|
| Regulation PDFs | ✅ 3 loaded (`sources.json` has real deep links, 0 placeholders) |
| Groq + Gemini keys | ✅ multi-key rotation, dual-provider failover |
| Deploy | ✅ Azure, auto-deploys on green CI against `main` |
| Corpus re-ingest after PR #21 | ⬜ **R2 above** |
| IEGC PDF | ⬜ **R1 above** — needs a human |
| `generate_briefing()` wiring | ⬜ deferred; needs a schema change |

> **Dense embeddings remain unbuilt, deliberately.** 179 chunks, 0 embeddings — retrieval is
> BM25-only, and `recall@5 = 0.73` already clears the 0.70 target. Installing torch and a 2.2 GB
> BGE-M3 model on the demo box would chase a metric that is passing, and **cannot** fix the misses,
> which are missing documents (R1). Revisit after the corpus gap closes, not before.

### Meet Virugama — ML (~80%)

**Delivered:** the DSM engine (X-trajectory by date, frequency bands, seller-side rules, YAML for
2024/2026/2031), and — new — a retrained, calibrated, serving forecast.

`prediction_bundle/models_v2/`, built by `scripts/train_forecast.py`:

| | |
|---|---|
| MAE | 0.0552 capacity factor |
| Skill vs persistence | **+21.5%** |
| P10–P90 coverage | **85.9%** (nominal 80%) |
| Physics | non-negative, within capacity, ordered, zero at night |

All six changes listed in the previous audit were made: leaking features dropped, `PLANT_ID`
removed entirely rather than fixed, capacity-factor target, non-negativity enforced, chronological
splits, conformal calibration rebuilt on a held-out window.

**Known limits, recorded in `MANIFEST.json` rather than only here:**

- 2,774 rows / **29.9 days** / **1 plant**. Not enough for rolling-origin CV.
- Cross-plant use is a **capacity-factor transfer from a reference site**, not a per-plant model.
  Say so when presenting it.
- All three horizons are retrained and served: +21.5% (24 h), +26.9% (48 h) and +32.5% (72 h) skill
  vs persistence. The 48 h and 72 h models drop generation lags that would not exist at issue time.
  The Forecast page has a 24 / 48 / 72 h switch.
- Forecasts depend on Open-Meteo being reachable. Verified 0.5 s from the VM; cached 15 min per
  plant and date. `FORECAST_ENGINE_TYPE=mock` is the one-line rollback.

**Since the last audit:** wind is served by `physics.py` (turbine power curve), and the planned
battery LP was replaced by `battery_recourse.py`, because a fixed day-ahead battery plan cannot
lower a DSM penalty.

**Still missing** (none demo-critical): `calibration.py` and `ensemble.py` as separate modules
(calibration is applied inside `lgbm_model.py`), a persistence baseline module, and the evaluation
notebooks, so there is no backtest harness beyond what `train_forecast.py` prints and the manifest
records.

---

## Roadmap

### Phase 0 — Demo-critical

**Complete.** Every item from the previous audit is done: pooling correlation, frontend core,
regulation PDFs, Groq key, block numbering, deploy.

| # | Task | Owner | Time | Status |
|---|---|---|---|---|
| 1 | Re-ingest the corpus after PR #21 | M4 | 5m | ⬜ **R2** |
| 2 | Surface `serving_synthetic_data` in the UI | M3 | 30m | ⬜ |
| 3 | Demo script + failover rehearsal | all | 1h | ⬜ |

### Phase 1 — Raises answer quality (half a day)

| # | Task | Time |
|---|---|---|
| 4 | Source the IEGC PDF, ingest it | 1h + human |
| 5 | Correct the two wrong expectations in `rag_eval_questions.json` | 15m |
| 6 | Re-measure `recall@5` against the rebuilt corpus | 10m |
| 7 | `persistence.py` + a backtest notebook — evidence beyond the manifest | 4h |

### Phase 2 — Completes the plan (1–2 weeks)

`calibration.py` and `ensemble.py` as modules, a persistence baseline, the evaluation notebooks,
a scheduler on the Azure VM, `generate_briefing()` wired into the pipeline, `/dashboard/{plant_id}` adopted
by the UI, dense embeddings **if** R1 is closed first.

### Explicitly descoped

Chronos-2 (`chronos_model.py`, notebooks 06/07) — not built, not needed for any demo claim, and now
removed from the README.

---

## What you can honestly claim today

✅ A forecast that is **real and measured** — +21.5% skill over persistence, 85.9% band coverage,
   conformally calibrated, with its limits written into the model manifest
✅ CERC 2026 seller-side DSM pricing with X-trajectory — real, tested
✅ Min-₹ schedule optimisation — measured against a calibrated band (15.5% on 13 Sept; varies by day)
✅ Portfolio pooling — measured, correlation assumption declared (25.6% on 13 Sept)
✅ Live weather ingestion — Open-Meteo → validation → 15-min IST blocks → DB
✅ Action cards — each carrying a real rupee delta
✅ A copilot that **structurally cannot** invent a ₹ figure — guardrail enforced post-generation
✅ A real React dashboard, deployed, wired to all of it
✅ Engine transparency — `/health` reports `serving_synthetic_data`, and it is **empty**

⚠️ Trained on one plant over 29.9 days; applied to four via capacity-factor transfer
⚠️ Wind is physics-only, with no generation data to validate it against
⚠️ Citations currently skew to the 2024 commentary document (R1)

### The strongest honest framing

Don't present this as a forecasting project — everyone forecasts. Present the **decision layer**:
pricing deviation in rupees under real CERC rules, optimising the schedule against it, netting it
across a portfolio, and explaining it with citations that cannot fabricate money.

And demo the refusals, because they are the part most teams will not have:

> "Our first trained models were rejected by our own physics gate — 22× scale mismatch, and they
> predicted solar generation at midnight. So we retrained without the three features that leak the
> answer, and calibrated the band conformally because raw quantile regression only covered 71.5%
> against a nominal 80%. `/health` will tell you which parts of this dashboard are synthetic.
> Right now the list is empty."

That is a stronger story than an accuracy number. It only works if the UI shows the badge — which
is why item 2 above is worth its 30 minutes.
