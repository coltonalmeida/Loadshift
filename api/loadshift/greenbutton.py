"""Green Button (ESPI) XML parsing and what-if analysis.

Ontario Reg. 633/21 gives customers standardized smart-meter interval data.
We join hourly usage with our historical MEF labels and ask: what if the
deferrable share of each day's load had run in that day's cleanest 4-hour
window? DEFERRABLE_SHARE is a stated assumption (see ASSUMPTIONS.md).
"""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

ESPI_NS = "http://naesb.org/espi"
DEFERRABLE_SHARE = 0.30
CLEAN_WINDOW_H = 4

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
SAMPLE_PATH = Path(__file__).resolve().parents[1] / "samples" / "sample_greenbutton.xml"


def parse(xml_bytes: bytes) -> pd.Series:
    """Hourly kWh series (UTC naive index) from any ESPI feed nesting."""
    root = ET.fromstring(xml_bytes)
    rows = []
    for reading in root.iter(f"{{{ESPI_NS}}}IntervalReading"):
        start = reading.findtext(f"{{{ESPI_NS}}}timePeriod/{{{ESPI_NS}}}start")
        value = reading.findtext(f"{{{ESPI_NS}}}value")
        if start is None or value is None:
            continue
        rows.append((int(start), float(value)))
    if not rows:
        raise ValueError("no IntervalReading elements found — is this an ESPI file?")
    s = pd.Series(dict(rows)).sort_index()
    s.index = pd.to_datetime(s.index, unit="s")
    # ESPI values are Wh; resample to hourly kWh
    return s.resample("h").sum().div(1000).rename("kwh")


def analyze(kwh: pd.Series) -> dict:
    hist = pd.read_parquet(ARTIFACTS / "mef_history.parquet")
    joined = kwh.to_frame().join(hist, how="inner").dropna()
    if len(joined) < 24 * 7:
        raise ValueError("less than a week of overlap with our MEF history (2024+)")

    joined["g"] = joined["kwh"] * joined["mef"]
    actual_g = float(joined["g"].sum())

    day = joined.groupby(joined.index.date)
    daily_kwh = day["kwh"].sum()
    mean_mef = day["mef"].mean()
    min_window_mef = day["mef"].apply(
        lambda s: s.rolling(CLEAN_WINDOW_H).mean().min() if len(s) >= CLEAN_WINDOW_H else s.mean()
    )
    savings_g = float((DEFERRABLE_SHARE * daily_kwh * (mean_mef - min_window_mef)).sum())

    monthly = (
        joined.assign(month=joined.index.strftime("%Y-%m"))
        .groupby("month")
        .agg(kwh=("kwh", "sum"), g=("g", "sum"))
        .round(1)
    )
    return {
        "period": [str(joined.index.min().date()), str(joined.index.max().date())],
        "total_kwh": round(float(joined["kwh"].sum()), 1),
        "actual_kg": round(actual_g / 1000, 2),
        "optimal_kg": round((actual_g - savings_g) / 1000, 2),
        "saved_kg": round(savings_g / 1000, 2),
        "pct_saving": round(100 * savings_g / actual_g, 1),
        "assumption": f"{int(DEFERRABLE_SHARE*100)}% of daily load shifted into "
                      f"that day's cleanest {CLEAN_WINDOW_H}h window",
        "monthly": [
            {"month": m, "kwh": float(r["kwh"]), "kg": round(float(r["g"]) / 1000, 1)}
            for m, r in monthly.iterrows()
        ],
    }
