"""Seasonal-naive baseline: mef(t) = mef(t - 168h). The bar the model must beat."""
from __future__ import annotations

import pandas as pd


def seasonal_naive(mef: pd.Series, hours: int = 168) -> pd.Series:
    return mef.shift(hours).rename("mef_naive")
