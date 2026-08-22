"""Green Button (ESPI) XML parsing and what-if analysis.

Ontario Reg. 633/21 gives customers standardized smart-meter interval data.
We join hourly usage with our historical MEF labels and ask: what if the
deferrable share of each day's load had run in that day's cleanest 4-hour
window? DEFERRABLE_SHARE is a stated assumption (see ASSUMPTIONS.md).

The same shift is priced under the OEB Time-of-Use and Ultra-Low Overnight
plans, so results carry both grams and dollars.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import pandas as pd

from . import config, pricing

ESPI_NS = "http://naesb.org/espi"
DEFERRABLE_SHARE = 0.30
CLEAN_WINDOW_H = 4
TZ = ZoneInfo("America/Toronto")

SAMPLE_PATH = config.SAMPLES / "sample_greenbutton.xml"


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
    hist = pd.read_parquet(config.ARTIFACTS / "mef_history.parquet")
    joined = kwh.to_frame().join(hist, how="inner").dropna()
    if len(joined) < 24 * 7:
        raise ValueError("less than a week of overlap with our MEF history (2024+)")

    joined["g"] = joined["kwh"] * joined["mef"]
    actual_g = float(joined["g"].sum())
    total_kwh = float(joined["kwh"].sum())

    # ── carbon: shift the deferrable share into each day's cleanest window ──
    day = joined.groupby(joined.index.date)
    daily_kwh = day["kwh"].sum()
    mean_mef = day["mef"].mean()
    min_window_mef = day["mef"].apply(
        lambda s: s.rolling(CLEAN_WINDOW_H).mean().min() if len(s) >= CLEAN_WINDOW_H else s.mean()
    )
    savings_g = float((DEFERRABLE_SHARE * daily_kwh * (mean_mef - min_window_mef)).sum())

    # ── money: the same shift, priced under both OEB plans ──
    rates_tou = pricing.series_rates(joined.index, "tou")
    rates_ulo = pricing.series_rates(joined.index, "ulo")
    cost_tou = float((joined["kwh"] * rates_tou).sum())        # cents
    cost_ulo = float((joined["kwh"] * rates_ulo).sum())
    rday = pd.DataFrame({"kwh": joined["kwh"], "rate": rates_tou}).groupby(joined.index.date)
    mean_rate = rday.apply(lambda d: d["rate"].mean())
    min_window_rate = rday.apply(
        lambda d: d["rate"].rolling(CLEAN_WINDOW_H).mean().min()
        if len(d) >= CLEAN_WINDOW_H else d["rate"].mean()
    )
    savings_cents_tou = float((DEFERRABLE_SHARE * daily_kwh * (mean_rate - min_window_rate)).sum())

    # ── habits: where the usage actually sits ──
    local_hours = joined.index.tz_localize("UTC").tz_convert(TZ).hour
    by_hour = joined["kwh"].groupby(local_hours).mean()
    usage_by_hour = [round(float(by_hour.get(h, 0.0)), 3) for h in range(24)]
    evening_share = float(joined["kwh"][(local_hours >= 17) & (local_hours < 21)].sum() / total_kwh)
    overnight_share = float(joined["kwh"][(local_hours >= 23) | (local_hours < 7)].sum() / total_kwh)
    # load-weighted MEF vs the period's time-flat mean: >1 = dirtier habits
    timing_score = float((actual_g / total_kwh) / joined["mef"].mean())

    worst = joined["g"].groupby(joined.index.date).sum().nlargest(3)
    worst_days = [{"date": str(d), "kg": round(g / 1000, 1)} for d, g in worst.items()]

    monthly = (
        joined.assign(month=joined.index.strftime("%Y-%m"))
        .groupby("month")
        .agg(kwh=("kwh", "sum"), g=("g", "sum"))
        .round(1)
    )

    return {
        "period": [str(joined.index.min().date()), str(joined.index.max().date())],
        "total_kwh": round(total_kwh, 1),
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
        # habits
        "usage_by_hour": usage_by_hour,
        "evening_peak_share": round(evening_share, 3),
        "overnight_share": round(overnight_share, 3),
        "timing_score": round(timing_score, 3),
        "worst_days": worst_days,
        # money (dollars, OEB rates effective 2025-11-01)
        "cost_tou": round(cost_tou / 100, 2),
        "cost_ulo": round(cost_ulo / 100, 2),
        "saved_tou": round(savings_cents_tou / 100, 2),
        "rates_effective": pricing.RATES_EFFECTIVE,
    }
