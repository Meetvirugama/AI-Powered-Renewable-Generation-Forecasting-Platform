# Forecast Model Integration — status, blockers, and what retraining needs

**Owner:** Member 4 (integration) / Member 1 (models)
**Status:** adapter shipped and tested; **the models are not yet usable in production**

> [!CAUTION]
> **Human action required before `FORECAST_ENGINE_TYPE=production` can serve.**
> Three blockers exist in the trained models (target leakage, scale mismatch, negative predictions).
> Until they are fixed, all forecasts are synthetic (mock sine-wave). The API reports this honestly
> via `serving_synthetic_data` in `GET /health`.
>
> **What needs doing (summary):**
> 1. Member 1 retrains models on capacity factor, drops leaking features — see [What retraining has to change](#what-retraining-has-to-change).
> 2. Re-run `tests/test_forecast_lgbm.py` — the physics gate must pass, not raise.
> 3. Set `FORECAST_ENGINE_TYPE=production` and verify `GET /health` no longer lists `forecast` under `serving_synthetic_data`.

This documents why `FORECAST_ENGINE_TYPE=production` currently refuses to serve, what was
fixed to get that far, and exactly what has to change in training before it can be switched on.


---

## Summary

| Thing | State |
|---|---|
| `prediction_bundle/models/*.txt` — 12 boosters | present, load correctly |
| `backend/modules/forecast/lgbm_model.py` adapter | **built, 18 tests** |
| `lightgbm` dependency | added to `requirements.txt` |
| Factory silent fallback to mock | **fixed — now raises** |
| `/health` disclosing synthetic engines | **added** |
| Models producing a usable forecast | ❌ **blocked — retraining required** |

The adapter is finished and correct. It refuses to serve because the models, as trained,
cannot describe these plants. That refusal is the feature: the alternative is a flat line at
nameplate capacity that the DSM engine would price into confident, wrong rupee figures.

---

## What was broken, and was fixed

### 1. All 12 model files were unloadable on Windows

`core.autocrlf=true` (Git for Windows default) rewrote LF → CRLF on checkout. A LightGBM `.txt`
model is text by that heuristic and binary in practice — its parser is strict about line
structure, and a stray CR produces `Model format error, expect a tree here` and then **aborts
the process** (exit 127), which is not a catchable exception.

The corruption was invisible to inspection: the Git blob was always clean, so the files looked
fine in the repository and were broken in every working tree. A Docker image built from a
Windows checkout would have inherited the corrupted copies.

**Fixed** by `.gitattributes` marking model and data artefacts `binary`. Verified: 2,345 CR
bytes removed from one file alone; all 12 now load. `tests/test_forecast_lgbm.py::
test_model_files_have_no_crlf` is the regression guard. The adapter also repairs CRLF in
memory, with a warning, so a stale checkout degrades instead of killing the API.

### 2. `FORECAST_ENGINE_TYPE=production` silently served mock data

`factory.py` caught `ImportError`, logged a warning, and returned `MockForecastEngine`. The
mock emits a seeded sine wave; the **real** DSM engine prices it into real rupee figures; the
dashboard renders them identically to genuine output. Nothing in any response or in `/health`
distinguished the two.

**Fixed.** `_resolve()` now raises `ProductionEngineUnavailable` when an engine is explicitly
set to `production` and cannot be built. `/health` publishes `engines` and
`serving_synthetic_data`, so "are these numbers real?" is answerable from the API.

---

## Why the models still cannot serve

Three independent problems, all confirmed against the actual boosters.

### Blocker A — target leakage

Three of the 61 features are measured at the same instant as the `AC_POWER` target:

| Feature | Why it leaks |
|---|---|
| `DC_POWER` | inverter input for the same timestamp; ~25% of total model gain |
| `DAILY_YIELD` | cumulative energy that already includes the target |
| `TOTAL_YIELD` | same, lifetime |

At forecast issue time for a future block these are unknowable. The adapter leaves them `NaN`
(LightGBM's native "unknown"), never 0.0 — filling zeros would be fabrication. But with the
single strongest feature absent, the model loses its diurnal signal and falls back on priors.

**Measured effect:** P50 at midnight = 139.2, P50 at noon = 287.7. A solar plant produces
*nothing* at midnight. The model cannot tell night from day without `DC_POWER`.

### Blocker B — scale and plant mismatch

From the boosters' own `feature_infos`:

```
PLANT_ID     none                      <- constant: trained on ONE plant
DC_POWER     [0 : 14413]               <- kW
TOTAL_YIELD  [6190002 : 7757913]
```

`PLANT_ID` is `none`, meaning it was constant during training — **these models saw a single
plant and cannot discriminate between the Gujarat plants in `config/plants.yaml`.** The value
ranges match a kW-scale dataset, not a 50 MW plant.

Raw output peaks at **1,081.9** against a configured capacity of **50 MW** — a 22× mismatch.
Clipping that to capacity produces a flat line at nameplate, which looks like a plant running
perfectly rather than like a broken forecast. That is precisely why the plausibility gate
checks the *raw* output, not just the clipped series.

### Blocker C — negative predictions

Raw minimum is **−1.43**. Generation cannot be negative.

---

## The plausibility gate

`LGBMForecastEngine._assert_physically_plausible()` refuses output that cannot describe the
plant it claims to describe:

- raw peak more than 10× plant capacity → scale mismatch
- raw values below zero
- solar generation above 2% of capacity during night hours (21:00–05:00 IST)

It raises `ImplausibleForecast` naming the specific violation and pointing here. This exists
because the DSM engine will price *any* MW series it is handed, and the dashboard renders the
result without further checks — so a model problem has to fail at the model, loudly, before it
becomes a financial claim.

Current output on the real models:

```
production forecast rejected as physically implausible:
  - raw model output peaks at 1,081.9 against a plant capacity of 50 MW -- a 22x scale
    mismatch, consistent with the models having been trained in kW on a different plant.
  - raw model output goes negative (-1.43)
  - 32 night-time blocks predict solar generation above 1.00 MW (worst: 50.00 MW at 00:00 IST).
```

---

## What retraining has to change

1. **Drop the leaking features.** Remove `DC_POWER`, `DAILY_YIELD`, `TOTAL_YIELD` from the
   feature set entirely. Expect headline accuracy to fall — the previous figures were partly
   measuring "given DC power, infer AC power", which is an inverter efficiency calculation,
   not a forecast.
2. **Train per plant, or make `PLANT_ID` a real categorical.** It is currently constant, so
   the models cannot represent more than one site.
3. **Predict in the platform's units.** Either train on MW or record an explicit scale factor
   in `PREDICTION_CONTRACT.json` that the adapter can apply.
4. **Constrain to non-negative.** Clip at training time or use an objective that cannot go
   below zero.
5. **Chronological splits, not random.** All three horizons report 373 test rows, which points
   to one random `train_test_split`. For a time series that leaks future into past.
6. **Rebuild conformal calibration on a held-out window.** `FINAL_VALIDATION_REPORT.json`
   already caveats this.

Point 6 has a data constraint worth naming: the dataset is ~2,774 rows at 15-minute
resolution, which is **≈29 days**, not the 34 sometimes quoted. Meaningful rolling-origin
cross-validation needs months, so honest validation may require more data before it is
possible at all.

---

## When the models are ready

```bash
pip install -r requirements.txt          # lightgbm included
export FORECAST_ENGINE_TYPE=production
curl localhost:8000/health | jq '.engines, .serving_synthetic_data, .forecast_models'
```

`serving_synthetic_data` should no longer list `forecast`, and `forecast_models.status` should
be `ok`. Then revisit `tests/test_forecast_lgbm.py::test_rejects_output_that_violates_physics`
— once the models are correct, a *passing* forecast is the expected outcome and that test
should be inverted to assert plausibility instead.

---

## Corrections to the circulated ML audit

For the record, checked against the tree:

- **Files that do not exist**, despite being cited as confirmed: `evidence/
  model_benchmark_results.csv`, `evidence/feature_importance.csv`, `evidence/
  global_top_drivers.csv`, `evidence/true_future_production_forecast.csv`, `evidence/
  temporal_stability_results.csv`, `evidence/probabilistic_validation_results.csv`,
  `registry/champion_vs_challenger.csv`, `registry/model_registry.csv`,
  `registry/promotion_log.csv`. `registry/` contains only `MODEL_LIFECYCLE_MASTER.xlsx`;
  `evidence/` contains only `AUDIT_REPORT.json`, `FINAL_EXECUTIVE_SUMMARY.md`,
  `FINAL_VALIDATION_REPORT.json`.
- **The 19-quantile claim is wrong**, as the audit itself notes — the contract declares
  `[0.1, 0.5, 0.9]` and only those three are trained. The API schema wants seven, so
  `p05/p25/p75/p95` are interpolated and labelled `interpolated_quantiles` in every block.
- **The CRLF corruption is not mentioned anywhere in the audit**, and it was the actual
  blocker: nothing else could work until it was fixed.
- **`PLANT_ID` being constant is not mentioned**, and it means the models cannot serve a
  multi-plant portfolio at all — a more fundamental limit than any of the listed gaps.
