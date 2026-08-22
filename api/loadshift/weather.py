"""Open-Meteo fetchers. All timestamps UTC to match ieso.py."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

WEATHER_COLS = ["temperature_2m", "wind_speed_100m", "cloud_cover", "shortwave_radiation"]

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"

# Last good live forecast. Lets an hourly refresh that hits a rate limit reuse
# real weather instead of failing the whole rebuild.
LAST_GOOD = DATA_DIR / "weather_forecast_last.json"

# Committed snapshot. api/data/ is wiped on every Render deploy, so an instance
# that boots straight into an Open-Meteo 429 has no last-good to fall back on
# and would serve 503 until the limit clears. This ships in the repo so the
# forecast degrades loudly instead of disappearing.
SEED = ARTIFACTS_DIR / "weather_seed.json"

# Beyond this the stored diurnal shape is too old to stand in for live weather.
FALLBACK_MAX_AGE_H = 72


def _to_frame(hourly: dict) -> pd.DataFrame:
    df = pd.DataFrame(hourly)
    df["ts"] = pd.to_datetime(df.pop("time"))
    return df.set_index("ts")[WEATHER_COLS]


def history(start: str, end: str) -> pd.DataFrame:
    """Hourly weather archive [start, end], UTC index. Cached to api/data/."""
    from . import config

    DATA_DIR.mkdir(exist_ok=True)
    cache = DATA_DIR / f"weather_{start}_{end}.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        url = config.OPEN_METEO_ARCHIVE.format(start=start, end=end).replace(
            "timezone=America%2FToronto", "timezone=UTC"
        )
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        payload = r.json()
        cache.write_text(json.dumps(payload))
    return _to_frame(payload["hourly"])


def _fetch_live(days: int, attempts: int) -> dict:
    """Open-Meteo forecast payload. Retries: 429s here are usually transient
    bursts on Render's shared egress IP, not an exhausted daily quota."""
    from . import config

    url = config.OPEN_METEO_FORECAST.format(days=days).replace(
        "timezone=America%2FToronto", "timezone=UTC"
    )
    last: Exception | None = None
    for i in range(attempts):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 - retry any transport/status error
            last = e
            if i < attempts - 1:
                time.sleep(2 ** i)
    raise last  # type: ignore[misc]


def _store_last_good(payload: dict) -> None:
    try:
        DATA_DIR.mkdir(exist_ok=True)
        LAST_GOOD.write_text(
            json.dumps({"fetched_at": _utcnow().isoformat(), "payload": payload})
        )
    except OSError as e:  # a read-only disk must not fail an otherwise good refresh
        print(f"[weather] could not store last-good: {type(e).__name__}: {e}")


def _utcnow() -> pd.Timestamp:
    return pd.Timestamp.utcnow().tz_localize(None)


def _load_stored(path: Path) -> tuple[pd.DataFrame, float] | None:
    """(frame, age_hours) from a stored snapshot, or None if unusable."""
    try:
        blob = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    payload = blob.get("payload")
    fetched = blob.get("fetched_at")
    if not payload or not fetched:
        return None
    try:
        age_h = (_utcnow() - pd.Timestamp(fetched)).total_seconds() / 3600
        return _to_frame(payload["hourly"]), float(age_h)
    except (KeyError, ValueError):
        return None


def forecast(days: int = 3, attempts: int = 3) -> pd.DataFrame:
    """Hourly weather forecast, UTC index. Live, else the newest usable
    snapshot. `df.attrs["source"]` is one of live/last_good/seed."""
    try:
        payload = _fetch_live(days, attempts)
        _store_last_good(payload)
        df = _to_frame(payload["hourly"])
        df.attrs["source"], df.attrs["age_h"] = "live", 0.0
        return df
    except Exception as live_error:  # noqa: BLE001 - fall back below
        print(f"[weather] live fetch failed: {type(live_error).__name__}: {live_error}")

    for name, path in (("last_good", LAST_GOOD), ("seed", SEED)):
        got = _load_stored(path)
        if got is None:
            continue
        df, age_h = got
        # The seed is deliberately exempt: an old snapshot's diurnal shape is a
        # far better answer than no site at all, and the payload says so.
        if name == "last_good" and age_h > FALLBACK_MAX_AGE_H:
            continue
        print(f"[weather] falling back to {name} ({age_h:.1f}h old)")
        df.attrs["source"], df.attrs["age_h"] = name, age_h
        return df

    raise RuntimeError("weather unavailable: live fetch failed and no usable snapshot")


def by_hour_of_day(df: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Project a stale snapshot onto `index` by UTC hour-of-day mean.

    A snapshot whose timestamps have passed reindexes to all-NaN, which throws
    away a perfectly good diurnal shape. Averaging each clock hour keeps the
    daily temperature/solar cycle the model leans on. Approximation, flagged in
    the payload and in ASSUMPTIONS.md.
    """
    means = df.groupby(df.index.hour)[WEATHER_COLS].mean()
    out = means.reindex(index.hour)
    out.index = index
    return out


def aligned(index: pd.DatetimeIndex, days: int = 3) -> pd.DataFrame:
    """Weather covering `index`, live where possible. Carries source/age in
    .attrs so the caller can label the forecast honestly."""
    df = forecast(days=days)
    source = df.attrs.get("source", "live")
    if source == "live":
        out = df.reindex(index)
        # A live response that simply doesn't reach far enough is still stale
        # for the uncovered hours; patch them rather than feed the model NaN.
        if out[WEATHER_COLS].isna().any().any():
            out = out.fillna(by_hour_of_day(df, index))
    else:
        out = by_hour_of_day(df, index)
    out.attrs["source"] = source
    out.attrs["age_h"] = df.attrs.get("age_h", 0.0)
    return out
