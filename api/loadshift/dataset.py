"""Join IESO fuel mix + demand + weather into the hourly training dataset."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import config, ieso, weather


def average_intensity(fuel_df: pd.DataFrame) -> pd.Series:
    """Generation-weighted average intensity, gCO2eq/kWh."""
    total = fuel_df[config.FUELS].sum(axis=1)
    grams = sum(
        fuel_df[f].fillna(0) * ef for f, ef in config.EMISSION_FACTORS.items()
    )
    return (grams / total).rename("avg_intensity")


def build(start: str = config.TRAIN_START) -> pd.DataFrame:
    """Hourly dataset from `start` to now. UTC index.

    Columns: FUELS (MW), market_demand, ontario_demand, weather x4,
             net_demand, avg_intensity, plus local-time feature columns.
    """
    this_year = dt.date.today().year
    start_year = int(start[:4])

    fuel = pd.concat(
        [ieso.fuel_mix_year(y, live=(y == this_year)) for y in range(start_year, this_year + 1)]
    )
    demand = pd.concat(
        [ieso.demand_year(y, live=(y == this_year)) for y in range(start_year, this_year + 1)]
    )
    # Archive lags realtime by ~5 days; fill the tail with the forecast API's past days later.
    end = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    wx = weather.history(start, end)

    df = fuel.join(demand, how="inner").join(wx, how="left")
    df = df.loc[start:]

    # Full hourly grid; interpolate short source gaps (e.g. the single missing
    # hour at 2025-05-01 05:00 UTC, IESO Market Renewal go-live).
    full = pd.date_range(df.index.min(), df.index.max(), freq="h")
    df = df.reindex(full)
    df.index.name = "ts"
    ieso_cols = config.FUELS + ["market_demand", "ontario_demand"]
    df[ieso_cols] = df[ieso_cols].interpolate(limit=3)

    # Interpolate short weather gaps (archive tail); IESO data is left untouched.
    df[weather.WEATHER_COLS] = df[weather.WEATHER_COLS].interpolate(limit=48)

    df["net_demand"] = (
        df["ontario_demand"] - df["WIND"].fillna(0) - df["SOLAR"].fillna(0)
    )
    df["avg_intensity"] = average_intensity(df)

    return add_time_features(df)


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Local-wall-clock features (America/Toronto) from the UTC index."""
    local = df.index.tz_localize("UTC").tz_convert(config.TIMEZONE)
    out = df.copy()
    out["hour_local"] = local.hour
    out["hour_sin"] = np.sin(2 * np.pi * local.hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * local.hour / 24)
    out["dow"] = local.dayofweek
    out["month"] = local.month
    out["is_weekend"] = (local.dayofweek >= 5).astype(int)
    return out


SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall"}
HOUR_BLOCKS = {h: ("night" if h < 6 else "morning" if h < 12 else "afternoon" if h < 18 else "evening")
               for h in range(24)}


def bucket_of(df: pd.DataFrame) -> pd.Series:
    """season x hour-block bucket label per row (16 buckets)."""
    return (
        df["month"].map(SEASONS) + "_" + df["hour_local"].map(HOUR_BLOCKS)
    ).rename("bucket")
