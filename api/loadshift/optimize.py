"""Pick the lowest-emission contiguous window in the 24h forecast."""
from __future__ import annotations

import pandas as pd


def best_window(forecast: pd.Series, duration_h: int,
                allowed_starts: "pd.DatetimeIndex | None" = None) -> dict:
    """Sliding-window argmin over mean forecast MEF (gCO2/kWh).

    forecast: hourly marginal intensity, UTC index. allowed_starts optionally
    restricts which hours a run may START in (it may finish later — e.g. a
    dishwasher started before bed). The worst window is always unconstrained:
    savings are quoted against the worst the grid offers.
    """
    means = forecast.rolling(duration_h).mean().shift(-(duration_h - 1)).dropna()
    if means.empty:
        raise ValueError("forecast window shorter than duration")
    worst_start, worst_g = means.idxmax(), float(means.max())

    candidates = means
    if allowed_starts is not None:
        candidates = means[means.index.isin(allowed_starts)]
        if candidates.empty:
            raise ValueError("no forecast hours inside the allowed start window")
    best_start, best_g = candidates.idxmin(), float(candidates.min())
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
