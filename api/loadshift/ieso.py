"""IESO public-report fetchers and parsers.

Timing: IESO market reports use fixed Eastern STANDARD Time (UTC-5) year-round —
verified: DST transition days have exactly 24 rows. Hours are 1-24 ("hour ending"
convention aside, we treat hour h as the interval starting at h-1).
    timestamp_utc = date + (hour - 1)h + 5h
"""
from __future__ import annotations

import io
import time
from xml.etree import ElementTree as ET

import pandas as pd
import requests

from . import config

DATA_DIR = config.DATA

EST_OFFSET_H = 5  # IESO fixed EST -> UTC


def _fetch(url: str, cache_name: str | None = None, max_age_s: float | None = None) -> bytes:
    """GET with optional file cache in api/data/.

    max_age_s=None means any cached copy is fresh enough (historical files);
    otherwise re-fetch when the cached copy is older than max_age_s.
    """
    if cache_name:
        DATA_DIR.mkdir(exist_ok=True)
        path = DATA_DIR / cache_name
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if max_age_s is None or age < max_age_s:
                return path.read_bytes()
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    if cache_name:
        (DATA_DIR / cache_name).write_bytes(r.content)
    return r.content


def _est_to_utc(date: pd.Series, hour: pd.Series) -> pd.Series:
    return (
        pd.to_datetime(date)
        + pd.to_timedelta(hour - 1, unit="h")
        + pd.Timedelta(hours=EST_OFFSET_H)
    )


def fuel_mix_year(year: int, live: bool = False) -> pd.DataFrame:
    """Hourly generation by fuel for one year. Index: UTC timestamp; columns: FUELS (MW).

    live=True re-fetches if the cached copy is >1h old (use for the current year).
    """
    raw = _fetch(
        config.GEN_BY_FUEL_URL.format(year=year),
        cache_name=f"fuel_{year}.xml",
        max_age_s=3600 if live else None,
    )
    ns = {"n": config.NS_BY_FUEL}
    root = ET.fromstring(raw)
    rows = []
    for daily in root.iter(f"{{{config.NS_BY_FUEL}}}DailyData"):
        day = daily.findtext("n:Day", namespaces=ns)
        for hourly in daily.findall("n:HourlyData", ns):
            hour = int(hourly.findtext("n:Hour", namespaces=ns))
            row = {"date": day, "hour": hour}
            for ft in hourly.findall("n:FuelTotal", ns):
                fuel = ft.findtext("n:Fuel", namespaces=ns)
                out = ft.findtext("n:EnergyValue/n:Output", namespaces=ns)
                row[fuel] = float(out) if out is not None else None
            rows.append(row)
    df = pd.DataFrame(rows)
    df["ts"] = _est_to_utc(df["date"], df["hour"])
    df = df.set_index("ts").drop(columns=["date", "hour"]).sort_index()
    return df.reindex(columns=config.FUELS)


def demand_year(year: int, live: bool = False) -> pd.DataFrame:
    """Hourly Ontario demand for one year. Index: UTC; columns: market_demand, ontario_demand."""
    raw = _fetch(
        config.DEMAND_URL.format(year=year),
        cache_name=f"demand_{year}.csv",
        max_age_s=3600 if live else None,
    )
    df = pd.read_csv(io.BytesIO(raw), skiprows=3)
    df.columns = ["date", "hour", "market_demand", "ontario_demand"]
    df["ts"] = _est_to_utc(df["date"], df["hour"])
    return df.set_index("ts")[["market_demand", "ontario_demand"]].sort_index()


def live_generator_output() -> pd.DataFrame:
    """Today's per-generator hourly output from GenOutputCapability (namespace differs!).

    Returns hourly fuel totals for today. Index: UTC; columns: FUELS (MW).
    """
    raw = _fetch(config.GEN_CAPABILITY_URL)  # never cache: this is the live feed
    ns_uri = config.NS_CAPABILITY
    ns = {"n": ns_uri}
    root = ET.fromstring(raw)
    day = root.findtext(f".//{{{ns_uri}}}Date")
    rows: dict[tuple[str, int], float] = {}
    for gen in root.iter(f"{{{ns_uri}}}Generator"):
        fuel = gen.findtext("n:FuelType", namespaces=ns)
        for out in gen.findall("n:Outputs/n:Output", ns):
            hour = int(out.findtext("n:Hour", namespaces=ns))
            mw = out.findtext("n:EnergyMW", namespaces=ns)
            if mw is not None:
                rows[(fuel, hour)] = rows.get((fuel, hour), 0.0) + float(mw)
    df = pd.DataFrame(
        [{"fuel": f, "hour": h, "mw": v} for (f, h), v in rows.items()]
    ).pivot(index="hour", columns="fuel", values="mw")
    df.index = _est_to_utc(pd.Series([day] * len(df), index=df.index), df.index.to_series())
    df.index.name = "ts"
    return df.reindex(columns=config.FUELS).fillna(0.0)
