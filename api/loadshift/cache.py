"""Hourly cache refresh: fetch today's data, predict 24h, write forecast JSON.

Requests NEVER trigger this; APScheduler calls refresh() hourly. On any
upstream failure the last-known-good payload keeps being served with
stale=true â€” never an error page.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path

import pandas as pd

from . import config, dataset, ieso, mef, model, optimize, weather

CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "cache_forecast.json"
_lock = threading.Lock()
_state: dict = {"payload": None, "last_error": None, "attempts": 0}


def _recent_frame(hours: int = 240) -> pd.DataFrame:
    """Last ~10 days of joined fuel+demand with derived cols, UTC index."""
    year = dt.date.today().year
    fuel = ieso.fuel_mix_year(year, live=True)
    demand = ieso.demand_year(year, live=True)
    if len(fuel) < hours:  # early January: pull the previous year too
        fuel = pd.concat([ieso.fuel_mix_year(year - 1), fuel])
        demand = pd.concat([ieso.demand_year(year - 1), demand])
    df = fuel.join(demand, how="inner").tail(hours)

    # The yearly files update once a day; extend to the current hour with the
    # hourly GenOutputCapability live feed. Demand for those hours is estimated
    # as total generation x recent demand/generation ratio (stated approximation
    # — Ontario exports mean generation > demand).
    try:
        live = ieso.live_generator_output()
        live = live[live.index > df.index.max()]
        if len(live):
            ratio = (df["ontario_demand"] / df[config.FUELS].sum(axis=1)).tail(168).mean()
            ext = live.copy()
            ext["ontario_demand"] = ext[config.FUELS].sum(axis=1) * ratio
            ext["market_demand"] = float("nan")
            df = pd.concat([df, ext])
            df.attrs["intraday_rows"] = int(len(ext))
    except Exception as e:  # noqa: BLE001 - yearly data alone is still fine
        print(f"[cache] live extension skipped: {type(e).__name__}: {e}")

    df["net_demand"] = df["ontario_demand"] - df["WIND"].fillna(0) - df["SOLAR"].fillna(0)
    df["avg_intensity"] = dataset.average_intensity(df)
    return dataset.add_time_features(df)


def _build_payload() -> dict:
    curve = mef.MefCurve.load()
    booster = model.load_booster()
    recent = _recent_frame()
    recent_mef = curve.label(recent)

    now = pd.Timestamp.utcnow().floor("h").tz_localize(None)
    future_idx = pd.date_range(now + pd.Timedelta(hours=1), periods=24, freq="h")

    # Weather forecast covers the future index (fetched in UTC).
    wx = weather.forecast(days=3).reindex(future_idx)

    fut = pd.DataFrame(index=future_idx)
    for c in weather.WEATHER_COLS:
        fut[c] = wx[c]
    fut["ontario_demand"] = float("nan")  # only lags of demand are features
    fut = dataset.add_time_features(fut)

    # Lag features from recent history; tolerate the 1-2h IESO publication lag.
    def lagged(series: pd.Series, lag_h: int) -> pd.Series:
        want = future_idx - pd.Timedelta(hours=lag_h)
        return pd.Series(
            series.reindex(want, method="ffill", tolerance=pd.Timedelta(hours=3)).to_numpy(),
            index=future_idx,
        )

    fut["mef_lag24"] = lagged(recent_mef, 24)
    fut["mef_lag168"] = lagged(recent_mef, 168)
    fut["demand_lag24"] = lagged(recent["ontario_demand"], 24)
    fut["demand_lag168"] = lagged(recent["ontario_demand"], 168)
    roll = recent_mef.rolling(24).mean()
    fut["mef_roll24"] = lagged(roll, 24)

    pred = model.predict(booster, fut)

    card = json.loads((model.ARTIFACTS / "model_card.json").read_text())
    mae = card["mae_model"]

    # Average intensity forecast: seasonal naive (same hour yesterday) â€” for
    # the avg-vs-marginal comparison line only, labelled as an estimate.
    avg_naive = lagged(recent["avg_intensity"], 24)

    last = recent.iloc[-1]
    hours = [
        {
            "ts": ts.isoformat() + "Z",
            "marginal": round(float(pred[ts]), 1),
            "average": round(float(avg_naive[ts]), 1) if pd.notna(avg_naive[ts]) else None,
            "ci_low": round(float(pred[ts]) - 1.28 * mae, 1),
            "ci_high": round(float(pred[ts]) + 1.28 * mae, 1),
        }
        for ts in future_idx
    ]
    return {
        "generated_at": pd.Timestamp.utcnow().tz_localize(None).isoformat() + "Z",
        "stale": False,
        "now": {
            "ts": recent.index[-1].isoformat() + "Z",
            "marginal_gco2_kwh": round(float(recent_mef.iloc[-1]), 1),
            "average_gco2_kwh": round(float(last["avg_intensity"]), 1),
            "fuel_mix_mw": {f: round(float(last[f])) for f in config.FUELS},
            "ontario_demand_mw": round(float(last["ontario_demand"])),
            "demand_estimated": bool(recent.attrs.get("intraday_rows", 0)),
        },
        "hours": hours,
    }


def refresh() -> bool:
    """Rebuild the cache. Returns True on success; keeps last-good on failure."""
    with _lock:
        _state["attempts"] += 1
    try:
        payload = _build_payload()
    except Exception as e:  # noqa: BLE001 - any upstream failure -> serve stale
        print(f"[cache] refresh FAILED, serving stale: {type(e).__name__}: {e}")
        with _lock:
            # Surfaced on /api/health: a boot that never warms is otherwise
            # indistinguishable from one still in progress.
            _state["last_error"] = f"{type(e).__name__}: {e}"[:300]
            if _state["payload"]:
                _state["payload"]["stale"] = True
        return False
    with _lock:
        _state["last_error"] = None
        _state["payload"] = payload
        CACHE_PATH.parent.mkdir(exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload))
    print(f"[cache] refreshed at {payload['generated_at']}")
    return True


def diagnostics() -> dict:
    """Why the cache is empty, for operators. No secrets, no payload."""
    with _lock:
        return {"attempts": _state["attempts"], "last_error": _state["last_error"]}


def get() -> dict | None:
    """Current payload (memory, falling back to disk)."""
    with _lock:
        if _state["payload"] is None and CACHE_PATH.exists():
            p = json.loads(CACHE_PATH.read_text())
            p["stale"] = True  # disk copy is from a previous process
            _state["payload"] = p
        return _state["payload"]


def forecast_series() -> pd.Series:
    payload = get()
    if not payload:
        raise RuntimeError("cache empty")
    idx = pd.to_datetime([h["ts"].rstrip("Z") for h in payload["hours"]])
    return pd.Series([h["marginal"] for h in payload["hours"]], index=idx)
