# Roadmap — what is left, and the order to do it in

**Audited against `main` @ PR #21 merged**, and against the running production API at
`https://57.159.24.68.nip.io`. 290 tests passing, `ruff` clean, 0 CRLF-corrupted models.

Every claim below was verified against the tree or against the live system, not inferred from the
plan. Percentages are scope-completion estimates, not confidence.

---

## Where the project actually stands

| Track | Owner | Built | Demo-ready | Change |
|---|---|---|---|---|
| Backend / API / data | Member 2 | **99%** | ✅ yes | ↑ B2 fixed |
| Frontend | Member 3 | **85%** | ✅ yes | — |
| Infra / RAG copilot | Member 4 | **95%** | ✅ yes | ↑ corpus loaded, deployed |
| ML / forecasting | Member 1 | **80%** | ✅ yes | **↑ models retrained and serving** |

**Overall: ~92% built, ~90% demo-ready.**

The forecast going real is the change since the last audit. `/health` now reports
`serving_synthetic_data: []` — **nothing in the chain is mocked**.

Against the six-step value chain in the README:

| Step | State |
|---|---|
| 1. Ingest weather | ✅ real (Open-Meteo → validator → `weather_forecasts`) |
| 2. Forecast P05–P95 | ✅ **real** — LightGBM, +21.5% skill vs persistence, 85.9% band coverage |
| 3. Price in ₹ (CERC DSM) | ✅ real |
| 4. Optimise schedule | ✅ real — **30.2%** reduction, measured on the real forecast |
| 5. Flag grid actions | ✅ real (derived from optimiser output) |
| 6. Explain with citations | ✅ real — 179 chunks, 3 CERC documents, recall@5 = 0.73 |
| — Portfolio pooling | ✅ real — **34.5%**, measured, correlation assumption declared |

> Numbers moved when the forecast became real. The optimiser previously read 23–28% against a
> mock forecast whose spread was chosen by hand; 30.2% is measured against a calibrated band.

---

## 🔴 Remaining blockers

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

### Member 3 — Frontend (~85%)

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

### Member 2 — Backend (~99%)

11 endpoints, 10 tables + migrations, ingestion wired, `/pipeline/run` async with 202, API-key
auth enforced, zero TODO markers.

**B2 (IST block numbering) — FIXED.** `resampler.py` derives `block_no` from the IST wall clock
and the function carries the reasoning.

**Remaining:** nothing demo-critical.

### Member 4 — Infra + RAG (~95%)

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

### Member 1 — ML (~80%)

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
- **Only the 24h horizon** is retrained. 48h and 72h fall back to it — a worse forecast, where the
  legacy boosters for those horizons would have been a dishonest one.
- Forecasts depend on Open-Meteo being reachable. Verified 0.5 s from the VM; cached 15 min per
  plant and date. `FORECAST_ENGINE_TYPE=mock` is the one-line rollback.

**Still missing** (none demo-critical): `physics.py`, `calibration.py`, `ensemble.py`,
`battery_lp.py`, `test_physics.py`, all 10 notebooks — so there is no backtest harness or
evaluation report beyond what `train_forecast.py` prints and the manifest records.

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

`physics.py`, `calibration.py`, `ensemble.py`, `battery_lp.py`, the notebooks,
`test_physics.py`, `generate_briefing()` wired into the pipeline, `/dashboard/{plant_id}` adopted
by the UI, dense embeddings **if** R1 is closed first.

### Explicitly descoped

Chronos-2 (`chronos_model.py`, notebooks 06/07) — in the README tech stack, absent from the repo,
not needed for any demo claim. **Either build it or remove it from the README** before a judge
greps for it.

---

## What you can honestly claim today

✅ A forecast that is **real and measured** — +21.5% skill over persistence, 85.9% band coverage,
   conformally calibrated, with its limits written into the model manifest
✅ CERC 2026 seller-side DSM pricing with X-trajectory — real, tested
✅ Min-₹ schedule optimisation — **30.2%** reduction, measured against a calibrated band
✅ Portfolio pooling — **34.5%**, measured, correlation assumption declared
✅ Live weather ingestion — Open-Meteo → validation → 15-min IST blocks → DB
✅ Action cards — each carrying a real rupee delta
✅ A copilot that **structurally cannot** invent a ₹ figure — guardrail enforced post-generation
✅ A real React dashboard, deployed, wired to all of it
✅ Engine transparency — `/health` reports `serving_synthetic_data`, and it is **empty**

⚠️ Trained on one plant over 29.9 days; applied to four via capacity-factor transfer
⚠️ 24h horizon only; longer lead times fall back to it
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
