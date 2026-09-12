#!/usr/bin/env python
"""Retrain the day-ahead quantile forecast, honestly.

    python scripts/train_forecast.py
    python scripts/train_forecast.py --horizon 24 --out prediction_bundle/models_v2

Why retrain at all
------------------
The shipped models were unusable, and `docs/model_integration.md` records why.
The decisive one: `DC_POWER` correlates **+1.0000** with the `AC_POWER` target.
It is the inverter's input for the same instant, so the model was computing
`AC = DC x efficiency` -- an efficiency calculation dressed as a forecast. At
forecast issue time DC_POWER is unknowable, and without it the old model lost
its entire signal and predicted solar generation at midnight.

What this script does differently
---------------------------------
1. **No target leakage.** DC_POWER, DAILY_YIELD and TOTAL_YIELD are dropped.

2. **No lookahead through lags.** A 24-hour-ahead forecast cannot see generation
   from 15 minutes ago. Only lags of at least the forecast horizon are kept --
   at 15-minute blocks that means `generation_lag_96` and beyond. The previous
   feature set included `generation_lag_1`, which is a second, quieter leak.

3. **Capacity factor as the target.** The model predicts `AC_POWER / capacity`
   in [0, 1] rather than raw kW. The training plant is a single site on a kW
   scale; the platform serves four Gujarat plants rated in MW. Predicting a
   ratio and multiplying by each plant's AvC at inference is what makes one
   model transferable, and it removes the 22x scale mismatch that made the old
   models emit 1,081 against a 50 MW plant.

4. **Chronological splits.** 60/20/20 by time, never shuffled. The previous run
   reported 373 test rows for every horizon, which is the signature of a single
   random `train_test_split` -- and on a time series that trains on the future.

5. **Judged against persistence.** A forecast that cannot beat "same block
   yesterday" is not worth serving, so the skill score is reported and a
   negative one is called out.

Honest limits, stated rather than buried
----------------------------------------
The dataset is ~2,774 rows over 29.9 days from **one** plant. That supports a
single chronological split; it does not support 5-fold rolling-origin CV, and it
cannot produce per-plant models. Applying this to the Gujarat sites is a
capacity-factor transfer from a reference plant, and should be described that
way.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BLOCKS_PER_HOUR = 4
QUANTILES = {"P10": 0.10, "P50": 0.50, "P90": 0.90}

# Measured simultaneously with the target; unknowable at forecast issue time.
LEAKING = ("DC_POWER", "DAILY_YIELD", "TOTAL_YIELD")

TARGET = "AC_POWER"
TIME_COL = "DATE_TIME"

# The label under other names. `target_24h/48h/72h` are the shipped dataset's
# labels for the other horizons -- each is the answer shifted forward in time --
# and `capacity_factor` is the label this script derives. Training on any of
# them is training on the answer.
#
# Their absence is worth stating plainly because including them by accident does
# not look like a bug: it produces a +93.7% skill score and a 0.0044 MAE, which
# reads as a spectacular model rather than a broken experiment. That is exactly
# what the first run of this script did.
TARGET_ALIASES = ("target_24h", "target_48h", "target_72h", "capacity_factor")

# Row identifiers. SOURCE_KEY names the inverter; learning it would tie the
# model to this plant's hardware.
IDENTIFIERS = ("PLANT_ID", "SOURCE_KEY")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", type=Path, default=Path("prediction_bundle/renewable_ml_dataset.csv.gz"))
    p.add_argument("--out", type=Path, default=Path("prediction_bundle/models_v2"))
    p.add_argument("--horizon", type=int, default=24, help="forecast lead time in hours")
    p.add_argument("--dry-run", action="store_true", help="train and report, write nothing")
    return p.parse_args()


def usable_features(df: pd.DataFrame, horizon_hours: int) -> list[str]:
    """Columns a forecaster could actually hold at issue time.

    Weather comes from the forecast. Time features are deterministic. Generation
    history is only usable at a lag of at least the horizon -- anything more
    recent is information from the future.
    """
    min_lag = horizon_hours * BLOCKS_PER_HOUR
    keep: list[str] = []

    for col in df.columns:
        if col in (TARGET, TIME_COL) or col in LEAKING or col in TARGET_ALIASES:
            continue
        if col in IDENTIFIERS:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue

        if col.startswith("generation_lag_"):
            lag = int(col.rsplit("_", 1)[1])
            if lag >= min_lag:
                keep.append(col)
            continue

        # Rolling means, rolling std and deltas are all computed over recent
        # blocks, so they carry the same lookahead as a short lag.
        if col.startswith(("generation_rolling_", "generation_change_")):
            continue

        # PLANT_ID is constant in this dataset -- it carries no information and
        # would anchor the model to one site.
        if col == "PLANT_ID" and df[col].nunique() <= 1:
            continue

        keep.append(col)

    return keep


def pinball(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    delta = y_true - y_pred
    return float(np.mean(np.maximum(q * delta, (q - 1) * delta)))


def main() -> int:
    args = parse_args()
    import lightgbm as lgb

    df = pd.read_csv(args.dataset)
    df[TIME_COL] = pd.to_datetime(df[TIME_COL])
    df = df.sort_values(TIME_COL).reset_index(drop=True)

    # Nameplate for the training plant. The 99.9th percentile rather than the max
    # so a single spurious spike does not shrink every capacity factor.
    capacity = float(np.percentile(df[TARGET], 99.9))
    df["capacity_factor"] = (df[TARGET] / capacity).clip(0.0, 1.0)

    features = usable_features(df, args.horizon)
    dropped_lags = [c for c in df.columns if c.startswith(("generation_lag_", "generation_rolling_", "generation_change_")) and c not in features]

    print(f"dataset   : {len(df)} rows, {df[TIME_COL].min()} -> {df[TIME_COL].max()}")
    print(f"capacity  : {capacity:,.1f} (99.9th pct of {TARGET})")
    print(f"horizon   : {args.horizon}h -> lags below {args.horizon * BLOCKS_PER_HOUR} blocks excluded")
    print(f"features  : {len(features)} usable")
    print(f"  dropped leaking : {', '.join(LEAKING)}")
    print(f"  dropped lookahead: {len(dropped_lags)} lag/rolling columns")
    print()

    # Chronological, never shuffled.
    n = len(df)
    train_end, calib_end = int(n * 0.60), int(n * 0.80)
    train, calib, test = df.iloc[:train_end], df.iloc[train_end:calib_end], df.iloc[calib_end:]
    print(f"train     : {len(train):5d} rows  {train[TIME_COL].min().date()} -> {train[TIME_COL].max().date()}")
    print(f"calibrate : {len(calib):5d} rows  {calib[TIME_COL].min().date()} -> {calib[TIME_COL].max().date()}")
    print(f"test      : {len(test):5d} rows  {test[TIME_COL].min().date()} -> {test[TIME_COL].max().date()}")
    print()

    # A feature that is almost perfectly correlated with the label is the label.
    # This check is here because the first version of this script trained on
    # `capacity_factor` itself and reported a +93.7% skill score -- a leak does
    # not announce itself as a bug, it announces itself as a brilliant result.
    suspicious = []
    for col in features:
        corr = df[col].corr(df["capacity_factor"])
        if pd.notna(corr) and abs(corr) > 0.98:
            suspicious.append((col, corr))
    if suspicious:
        print("REFUSING TO TRAIN -- these features are effectively the label:")
        for col, corr in suspicious:
            print(f"  {col:32s} corr with target = {corr:+.4f}")
        return 1

    X_train, y_train = train[features], train["capacity_factor"]
    X_calib, y_calib = calib[features], calib["capacity_factor"]
    X_test, y_test = test[features], test["capacity_factor"]

    boosters, preds, calib_preds = {}, {}, {}
    for tag, q in QUANTILES.items():
        model = lgb.LGBMRegressor(
            objective="quantile", alpha=q,
            n_estimators=400, learning_rate=0.05, num_leaves=31,
            min_child_samples=20, subsample=0.9, colsample_bytree=0.9,
            random_state=42, verbose=-1,
        )
        model.fit(X_train, y_train)
        boosters[tag] = model
        # Generation cannot be negative and cannot exceed capacity.
        preds[tag] = np.clip(model.predict(X_test), 0.0, 1.0)
        calib_preds[tag] = np.clip(model.predict(X_calib), 0.0, 1.0)

    # Conformalised quantile regression (Romano et al., 2019).
    #
    # A quantile model fitted at 0.10 and 0.90 does not actually deliver 80%
    # coverage -- these came out at 73.2%, so the band understated the
    # uncertainty. That matters more here than a slightly-off point forecast:
    # the DSM optimiser chooses a schedule by weighting the quantiles, so a band
    # that is too narrow makes it over-confident and under-hedges the penalty.
    #
    # The correction is one number, learned on data the models never saw:
    # score each calibration row by how far outside the band it fell, take the
    # (1-alpha) quantile of those scores, and widen the band by it. Coverage is
    # then guaranteed on exchangeable data rather than hoped for.
    # Coverage of the raw quantile models, measured before any widening. It has
    # to be captured here: once the bands are widened and then row-sorted, the
    # original values cannot be recovered by subtracting delta back off.
    raw_cov = float(np.mean(
        (y_test.to_numpy() >= preds["P10"]) & (y_test.to_numpy() <= preds["P90"])
    ))

    conformity = np.maximum(
        calib_preds["P10"] - y_calib.to_numpy(),   # fell below the lower bound
        y_calib.to_numpy() - calib_preds["P90"],   # fell above the upper bound
    )
    n_calib = len(conformity)
    target_coverage = QUANTILES["P90"] - QUANTILES["P10"]        # 0.80
    # The (1+1/n) factor is the finite-sample correction; without it the
    # guarantee holds only asymptotically.
    level = min(1.0, (1 - (1 - target_coverage)) * (1 + 1 / n_calib))
    conformal_delta = float(np.quantile(conformity, level))
    conformal_delta = max(conformal_delta, 0.0)

    preds["P10"] = np.clip(preds["P10"] - conformal_delta, 0.0, 1.0)
    preds["P90"] = np.clip(preds["P90"] + conformal_delta, 0.0, 1.0)

    # Quantile models are fitted independently and can cross; sorting each row
    # guarantees P10 <= P50 <= P90 without refitting.
    stacked = np.sort(np.vstack([preds["P10"], preds["P50"], preds["P90"]]), axis=0)
    preds["P10"], preds["P50"], preds["P90"] = stacked[0], stacked[1], stacked[2]

    # Persistence: the same block one day earlier. The baseline any forecast has
    # to beat to justify existing.
    lag_col = f"generation_lag_{args.horizon * BLOCKS_PER_HOUR}"
    if lag_col in df.columns:
        persistence = (test[lag_col] / capacity).clip(0, 1).to_numpy()
    else:
        persistence = np.roll(df["capacity_factor"].to_numpy(), args.horizon * BLOCKS_PER_HOUR)[calib_end:]

    mae_model = float(np.mean(np.abs(y_test - preds["P50"])))
    mae_persist = float(np.mean(np.abs(y_test - persistence)))
    skill = 1 - mae_model / mae_persist if mae_persist > 0 else 0.0
    coverage = float(np.mean((y_test >= preds["P10"]) & (y_test <= preds["P90"])))

    print("RESULTS (capacity factor, 0-1)")
    print(f"  MAE  model       : {mae_model:.4f}  ({mae_model * capacity:,.1f} kW-equivalent)")
    print(f"  MAE  persistence : {mae_persist:.4f}")
    print(f"  skill vs persist : {skill:+.1%}  {'<-- worse than persistence' if skill < 0 else ''}")
    print(f"  P10-P90 coverage : {coverage:.1%}   (nominal 80%, {raw_cov:.1%} before conformal)")
    print(f"  conformal widen  : +/-{conformal_delta:.4f} capacity factor "
          f"({conformal_delta * capacity:,.0f} kW-equivalent)")
    for tag, q in QUANTILES.items():
        print(f"  pinball {tag}      : {pinball(y_test.to_numpy(), preds[tag], q):.5f}")
    print()

    print("PHYSICS CHECKS")
    night = test["hour"].isin([0, 1, 2, 3, 22, 23]) if "hour" in test else pd.Series(False, index=test.index)
    night_max = float(preds["P50"][night.to_numpy()].max()) if night.any() else 0.0
    checks = {
        "non-negative": bool((stacked >= 0).all()),
        "within capacity": bool((stacked <= 1.0).all()),
        "quantiles ordered": bool((preds["P10"] <= preds["P50"]).all() and (preds["P50"] <= preds["P90"]).all()),
        "near-zero at night": night_max < 0.02,
    }
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  (night max {night_max:.4f})" if "night" in name else ""))
    print()

    top = sorted(zip(features, boosters["P50"].feature_importances_), key=lambda kv: -kv[1])[:8]
    print("TOP FEATURES (P50)")
    for name, imp in top:
        print(f"  {imp:6.0f}  {name}")
    print()

    if args.dry_run:
        print("dry run: nothing written")
        return 0
    if not all(checks.values()):
        print("physics checks failed -- refusing to write models")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for tag, model in boosters.items():
        model.booster_.save_model(str(args.out / f"lightgbm_{args.horizon}h_{tag}.txt"))

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "horizon_hours": args.horizon,
        "target": "capacity_factor",
        "target_definition": f"{TARGET} / capacity, clipped to [0, 1]",
        "training_capacity": capacity,
        "apply_to_plant": "multiply the predicted capacity factor by that plant's avc_mw",
        "feature_order": features,
        "feature_count": len(features),
        "excluded_leaking": list(LEAKING),
        "excluded_lookahead": dropped_lags,
        "split": "chronological 60/20/20, never shuffled",
        "rows": {"train": len(train), "calibrate": len(calib), "test": len(test)},
        "conformal": {
            "delta_capacity_factor": conformal_delta,
            "method": "conformalised quantile regression (Romano et al. 2019)",
            "calibrated_on": "the held-out calibration split, never seen in training",
            "apply": "subtract delta from P10 and add it to P90, then clip to [0, 1]",
            "coverage_before": raw_cov,
            "coverage_after": coverage,
        },
        "metrics": {
            "mae_capacity_factor": mae_model,
            "mae_persistence": mae_persist,
            "skill_vs_persistence": skill,
            "coverage_p10_p90": coverage,
            "pinball": {t: pinball(y_test.to_numpy(), preds[t], q) for t, q in QUANTILES.items()},
        },
        "physics_checks": checks,
        "caveats": [
            "Trained on one plant over 29.9 days. Not enough for rolling-origin CV.",
            "Applying this to other plants is a capacity-factor transfer from a "
            "reference site, not a per-plant model. Say so when presenting it.",
        ],
    }
    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {len(boosters)} models + MANIFEST.json to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
