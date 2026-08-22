"""Hourly cache refresh: fetch today's data, predict 24h, write forecast JSON.

Requests NEVER trigger this. The Render cron job `loadshift-refresh` calls
refresh() hourly (see refresh_job.py); the web service only ever reads. On any
upstream failure the last-known-good payload keeps being served with
stale=true — never an error page.

Read order is Render Key Value first, then process memory, then local disk.
KV is what makes a freshly deployed instance warm: the container filesystem is
wiped on every deploy, so the disk tier only ever helps a restart-in-place.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time

import pandas as pd

from . import config, dataset, ieso, kv, weather

CACHE_PATH = config.DATA / "cache_forecast.json"

# How long a web instance may reuse its in-process copy before re-reading Key
# Value. The cron writes hourly, so a minute of skew is invisible to a visitor
# while keeping KV reads off the hot path of every single request.
_MEM_TTL_S = 60
# After a KV miss, retry sooner than a full TTL rather than sitting on a copy.
_MEM_RETRY_S = 5

_lock = threading.Lock()
_state: dict = {"payload": None, "last_error": None, "attempts": 0, "fetched_at": 0.0}


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
    # The one deferred import in this package, and it is load-bearing: `model`
    # pulls in LightGBM, and only the cron job ever reaches this function. The
    # web service imports cache.py to READ, and must not pay for a training-time
    # dependency to do it. Everything else imports at module scope.
    from . import mef, model

    curve = mef.MefCurve.load()
    booster = model.load_booster()
    recent = _recent_frame()
    recent_mef = curve.label(recent)

    now = pd.Timestamp.utcnow().floor("h").tz_localize(None)
    future_idx = pd.date_range(now + pd.Timedelta(hours=1), periods=24, freq="h")

    # Weather covering the future index (fetched in UTC). Falls back to a
    # stored snapshot rather than failing the whole rebuild; the source rides
    # along on the payload so a degraded forecast is never passed off as live.
    wx = weather.aligned(future_idx, days=3)
    wx_source = wx.attrs.get("source", "live")
    wx_age_h = round(float(wx.attrs.get("age_h", 0.0)), 1)

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

    card = json.loads((config.ARTIFACTS / "model_card.json").read_text())
    mae = card["mae_model"]

    # Average intensity forecast: seasonal naive (same hour yesterday) — for
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
        # Fallback weather means the marginal numbers are a degraded estimate,
        # which is exactly what stale already tells the UI to say.
        "stale": wx_source != "live",
        "weather_source": wx_source,
        "weather_age_h": wx_age_h,
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
        _state["fetched_at"] = time.monotonic()
        try:
            CACHE_PATH.parent.mkdir(exist_ok=True)
            CACHE_PATH.write_text(json.dumps(payload))
        except OSError as e:  # a read-only disk must not fail a good refresh
            print(f"[cache] local write failed: {type(e).__name__}: {e}")
    # The durable tier. This is what a redeployed web service reads on boot,
    # and the only copy that outlives the container that produced it.
    kv.set_json(kv.FORECAST_KEY, payload)
    print(f"[cache] refreshed at {payload['generated_at']}")
    return True


def diagnostics() -> dict:
    """Why the cache is empty, for operators. No secrets, no payload."""
    with _lock:
        return {"attempts": _state["attempts"], "last_error": _state["last_error"]}


def _disk() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        p = json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError) as e:
        print(f"[cache] local read failed: {type(e).__name__}: {e}")
        return None
    p["stale"] = True  # disk copy is from a previous process
    return p


def get() -> dict | None:
    """Current payload: Key Value, else process memory, else local disk.

    The in-process copy is only a read-through cache over Key Value, held for
    _MEM_TTL_S. Without that expiry a web instance would serve the payload it
    booted with forever while the cron job wrote newer ones every hour.
    """
    now = time.monotonic()
    with _lock:
        fresh = _state["payload"] is not None and now - _state["fetched_at"] < _MEM_TTL_S
        if fresh:
            return _state["payload"]

    p = _from_kv()
    if p is not None:
        with _lock:
            _state["payload"] = p
            _state["fetched_at"] = now
        return p

    # KV missed or is unreachable. Anything we already hold beats nothing, and
    # it is better than 503 — but re-check KV on the next call, not in an hour.
    with _lock:
        if _state["payload"] is not None:
            _state["fetched_at"] = now - _MEM_TTL_S + _MEM_RETRY_S
            return _state["payload"]

    p = _disk()
    if p is not None:
        with _lock:
            _state["payload"] = p
            _state["fetched_at"] = now - _MEM_TTL_S + _MEM_RETRY_S
    return p


def _from_kv() -> dict | None:
    """Payload written by the cron job, if Key Value has one.

    Not marked stale: a payload the cron wrote this hour is current, and it
    carries its own generated_at and stale flag for the UI to judge.
    """
    return kv.get_json(kv.FORECAST_KEY)


def forecast_series(payload: dict | None = None) -> pd.Series:
    """Hourly marginal forecast as a Series, from `payload` or the current cache.

    Callers that also need other fields off the payload should read it once and
    pass it in, so the series and those fields describe the same forecast.
    """
    payload = payload or get()
    if not payload:
        raise RuntimeError("cache empty")
    idx = pd.to_datetime([h["ts"].rstrip("Z") for h in payload["hours"]])
    return pd.Series([h["marginal"] for h in payload["hours"]], index=idx)
