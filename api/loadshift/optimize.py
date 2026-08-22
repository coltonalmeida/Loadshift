"""Pick the lowest-emission contiguous window in the 24h forecast."""
from __future__ import annotations

import pandas as pd


def best_window(forecast: pd.Series, duration_h: int,
                earliest: pd.Timestamp | None = None,
                latest: pd.Timestamp | None = None) -> dict:
    """Sliding-window argmin over mean forecast MEF (gCO2/kWh).

    forecast: hourly marginal intensity, UTC index. Returns best/worst window
    starts and the grid-determined percent saving (independent of kWh).
    """
    f = forecast
    if earliest is not None:
        f = f[f.index >= earliest]
    if latest is not None:
        f = f[f.index + pd.Timedelta(hours=duration_h) <= latest]
    if len(f) < duration_h:
        raise ValueError("forecast window shorter than duration")

    means = f.rolling(duration_h).mean().shift(-(duration_h - 1)).dropna()
    best_start, worst_start = means.idxmin(), means.idxmax()
    best_g, worst_g = float(means.min()), float(means.max())
    return {
        "best_start": best_start,
        "best_gco2_kwh": round(best_g, 1),
        "worst_start": worst_start,
        "worst_gco2_kwh": round(worst_g, 1),
        "pct_saving": round(100 * (worst_g - best_g) / worst_g, 1),
    }


def grams_saved(result: dict, kwh_range: tuple[float, float]) -> list[float]:
    """Absolute grams saved range for an appliance kWh range."""
    per_kwh = result["worst_gco2_kwh"] - result["best_gco2_kwh"]
    return [round(kwh_range[0] * per_kwh), round(kwh_range[1] * per_kwh)]
