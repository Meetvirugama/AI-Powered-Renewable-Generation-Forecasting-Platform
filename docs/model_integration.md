# Forecast Model Integration — how the production forecast came to be real

**Owner:** Member 4 (integration) / Member 1 (models)
**Status:** ✅ **resolved.** `FORECAST_ENGINE_TYPE=production` serves real forecasts.

> [!NOTE]
> **This document is now mostly history, and worth keeping as history.**
>
> It records why the original 12 boosters could not serve, what the physics gate refused and why,
> and what retraining had to change. All three blockers are fixed. The live API reports
> `serving_synthetic_data: []`.
>
> If you arrived here from an `ImplausibleForecast` error message, that error is the gate doing its
> job — most likely on the **legacy** bundle in `prediction_bundle/models/`, which is deliberately
> kept and still rejected. The models actually served are in `prediction_bundle/models_v2/`.

---

## Current state

| Thing | State |
|---|---|
| `prediction_bundle/models_v2/*.txt` — 3 boosters, 24h, 44 features | ✅ **serving** |
| `prediction_bundle/models/*.txt` — 12 legacy boosters | kept; still rejected by the gate |
| `backend/modules/forecast/lgbm_model.py` adapter | ✅ serves capacity factor → MW |
| `backend/modules/forecast/weather_provider.py` | ✅ supplies the 33 weather features |
| Factory silent fallback to mock | fixed — raises |
| `/health` disclosing synthetic engines | reports `serving_synthetic_data: []` |

Measured on a held-out chronological split, against persistence:

| | |
|---|---|
| MAE | 0.0552 capacity factor |
| Skill vs persistence | **+21.5%** |
| P10–P90 coverage | **85.9%** (nominal 80%; 71.5% before conformal calibration) |
| Physics | non-negative, within capacity, quantiles ordered, zero at night |

`prediction_bundle/models_v2/MANIFEST.json` is the contract: feature order, training capacity,
conformal delta, metrics, and the caveats. The adapter refuses to load if the manifest disagrees
with the boosters, because it carries numbers that silently change every rupee figure downstream.

### Limits that remain true

- 2,774 rows / **29.9 days** / **one plant**. Not enough for rolling-origin CV.
- Applying it to four Gujarat plants is a **capacity-factor transfer from a reference site**, not a
  per-plant model. Say so when presenting it.
- **Only the 24h horizon** was retrained. 48h and 72h fall back to it — worse, but honest; the
  legacy boosters for those horizons were trained on features that do not exist that far ahead.
- Forecasts now require Open-Meteo. Cached 15 minutes per plant and date;
  `FORECAST_ENGINE_TYPE=mock` is the one-line rollback.

### Why the legacy bundle is kept

Deleting it would delete the evidence. The physics gate rejecting those 12 boosters — 22× scale
mismatch, solar generation at midnight — is the reason the retrain happened, and
`tests/test_forecast_lgbm.py` asserts that it still rejects them. A refusal you can demonstrate is
worth more than a mistake you quietly removed.

---

## History: the adapter, and why it refused

Everything below describes the state before the retrain. It is kept because the failure modes are
the interesting part, and because the gate that caught them is still running.

The adapter was finished and correct. It refused to serve because the models, as trained,
could not describe these plants. That refusal was the feature: the alternative is a flat line at
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
test_no_model_file_has_crlf` is the regression guard. The adapter also repairs CRLF in
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

## Why the original models could not serve

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

Output of the gate on the legacy bundle (still reproducible today):

```
production forecast rejected as physically implausible:
  - raw model output peaks at 1,081.9 against a plant capacity of 50 MW -- a 22x scale
    mismatch, consistent with the models having been trained in kW on a different plant.
  - raw model output goes negative (-1.43)
  - 32 night-time blocks predict solar generation above 1.00 MW (worst: 50.00 MW at 00:00 IST).
```

---

## What retraining had to change — and what was done

All six are implemented in `scripts/train_forecast.py`.

| # | Required | What was done |
|---|---|---|
| 1 | Drop `DC_POWER`, `DAILY_YIELD`, `TOTAL_YIELD` | ✅ excluded, along with 13 generation lags and rolling windows shorter than the horizon. Of the lags only `generation_lag_96` survives — 96 blocks is exactly 24 h. Headline accuracy did fall, as predicted. |
| 2 | Fix `PLANT_ID` | ✅ **removed entirely** rather than fixed. Cross-plant transfer is handled by the capacity-factor target instead, which works with one plant's data; a categorical cannot. |
| 3 | Predict in the platform's units | ✅ target is `AC_POWER / capacity` in [0, 1]; `MANIFEST.json` records the training capacity and the adapter multiplies by each plant's `avc_mw`. |
| 4 | Constrain non-negative | ✅ clipped at training time and again at inference. |
| 5 | Chronological splits | ✅ 60/20/20, never shuffled. |
| 6 | Rebuild conformal calibration | ✅ conformalised quantile regression (Romano et al. 2019) on the middle split, which the boosters never saw. Raw coverage was 71.5% against a nominal 80%; calibrated, 85.9%. |

One guard was added that the audit did not ask for: training **refuses to run** if any feature
correlates above 0.98 with the label. The first run of the retrain script reported +93.7% skill,
which turned out to be the target left in the feature matrix. The guard exists so that particular
embarrassment cannot recur silently.

The data constraint named in the original audit stands and is now recorded in the manifest: 2,774
rows at 15-minute resolution is **29.9 days**, one plant. Rolling-origin cross-validation needs
months, so it was not attempted rather than faked.

---

## Verifying it end to end

```bash
pip install -r requirements.txt          # lightgbm included
export FORECAST_ENGINE_TYPE=production
curl localhost:8000/health | jq '.engines, .serving_synthetic_data, .forecast_models'
```

`serving_synthetic_data` should be `[]`, and `forecast_models.status` should be `ok` with
`target: "capacity_factor"`.

`tests/test_forecast_lgbm.py` was inverted as this section originally anticipated: a *passing*
forecast is now the expected outcome, asserted in plant-scale MW with the band widened and the
night clamped. The legacy bundle keeps a test of its own asserting that the gate still rejects it.

> One trap worth knowing if you write a test here. Use a **day-ahead** date and give the fixture
> zero irradiance outside 06:00–19:00 IST. A same-day request exercises a different weather window
> (see PR #20), and a fixture claiming sunlight at midnight asks the model a question it never saw
> in training — the night-time gate will correctly refuse the answer, and the test will look like a
> model failure when it is a fixture failure.

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
