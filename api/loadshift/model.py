"""LightGBM forecaster for marginal intensity, valid for horizons up to 24h.

Single direct model: every feature of target hour t is known at forecast time
t0 >= t - 24h — calendar and weather come from the forecast, and all lags are
>= 24h relative to t (mef/demand at t-24 and t-168, rolling-24h mean of mef
ending at t-24).
"""
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import baseline, config
from .weather import WEATHER_COLS

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"

CAL_COLS = ["hour_sin", "hour_cos", "dow", "month", "is_weekend"]
LAG_COLS = ["mef_lag24", "mef_lag168", "demand_lag24", "demand_lag168", "mef_roll24"]
FEATURES = CAL_COLS + WEATHER_COLS + LAG_COLS


def make_features(df: pd.DataFrame, mef: pd.Series) -> pd.DataFrame:
    """Feature frame aligned to df's index. All lags causal for a 24h horizon."""
    x = df[CAL_COLS + WEATHER_COLS].copy()
    x["mef_lag24"] = mef.shift(24)
    x["mef_lag168"] = mef.shift(168)
    x["demand_lag24"] = df["ontario_demand"].shift(24)
    x["demand_lag168"] = df["ontario_demand"].shift(168)
    x["mef_roll24"] = mef.shift(24).rolling(24).mean()
    return x


def train(df: pd.DataFrame, mef: pd.Series, holdout_days: int = 60) -> dict:
    """Train with a chronological split; returns metrics + writes artifacts."""
    x = make_features(df, mef)
    data = x.assign(target=mef).dropna()

    cut = data.index.max() - pd.Timedelta(days=holdout_days)
    val_cut = cut - pd.Timedelta(days=30)
    tr = data[data.index <= val_cut]
    va = data[(data.index > val_cut) & (data.index <= cut)]
    te = data[data.index > cut]

    model = lgb.LGBMRegressor(
        n_estimators=1500, learning_rate=0.04, num_leaves=63,
        subsample=0.9, colsample_bytree=0.9, random_state=7, verbose=-1,
    )
    model.fit(
        tr[FEATURES], tr["target"],
        eval_X=va[FEATURES], eval_y=va["target"],
        callbacks=[lgb.early_stopping(80, verbose=False)],
    )

    pred = pd.Series(model.predict(te[FEATURES]), index=te.index)
    naive = baseline.seasonal_naive(mef).reindex(te.index)
    mae_model = float((pred - te["target"]).abs().mean())
    mae_naive = float((naive - te["target"]).abs().mean())
    ss_res = float(((pred - te["target"]) ** 2).sum())
    ss_tot = float(((te["target"] - te["target"].mean()) ** 2).sum())

    ARTIFACTS.mkdir(exist_ok=True)
    model.booster_.save_model(ARTIFACTS / "model.txt")
    card = {
        "target": "marginal carbon intensity (gCO2eq/kWh), 24h-ahead",
        "model": "LightGBM, direct single-model, all lags >= 24h (causal)",
        "features": FEATURES,
        "train_rows": len(tr),
        "test_days": holdout_days,
        "test_range": [str(te.index.min()), str(te.index.max())],
        "mae_model": round(mae_model, 2),
        "mae_baseline_seasonal_naive_168h": round(mae_naive, 2),
        "improvement_pct": round(100 * (1 - mae_model / mae_naive), 1),
        "test_r2": round(1 - ss_res / ss_tot, 3),
        "target_mean": round(float(te["target"].mean()), 1),
        "emission_factors_gco2_kwh": config.EMISSION_FACTORS,
        "best_iteration": int(model.best_iteration_ or model.n_estimators),
    }
    (ARTIFACTS / "model_card.json").write_text(json.dumps(card, indent=1))
    return card


def load_booster() -> lgb.Booster:
    return lgb.Booster(model_file=str(ARTIFACTS / "model.txt"))


def predict(booster: lgb.Booster, features: pd.DataFrame) -> pd.Series:
    return pd.Series(booster.predict(features[FEATURES]), index=features.index, name="mef_pred")
