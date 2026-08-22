"""Open-Meteo fetchers. All timestamps UTC to match ieso.py."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

WEATHER_COLS = ["temperature_2m", "wind_speed_100m", "cloud_cover", "shortwave_radiation"]

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


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


def forecast(days: int = 3) -> pd.DataFrame:
    """Hourly weather forecast, UTC index. Never cached — always live."""
    from . import config

    url = config.OPEN_METEO_FORECAST.format(days=days).replace(
        "timezone=America%2FToronto", "timezone=UTC"
    )
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return _to_frame(r.json()["hourly"])
