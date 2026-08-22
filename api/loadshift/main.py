"""Loadshift API. Serves cached forecasts only — no model runs on request paths.

The hourly rebuild lives in the `loadshift-refresh` Render cron job, not here
(see refresh_job.py). This process reads Render Key Value and never imports
LightGBM. The only exception is the supervisor below, which rebuilds the forecast
itself when — and only when — nothing else is.
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import asynccontextmanager
from xml.etree.ElementTree import ParseError as ET_ParseError

import pandas as pd
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import (
    cache, config, greenbutton, insights, kv, optimize, pricing, ratelimit,
)

# A cron that reported in this recently is doing its job. One missed hourly run
# is not an emergency; two consecutive ones mean nobody is refreshing.
CRON_GRACE_S = 2 * 3600
# Matches the cron's own cadence: past this with no cron, we rebuild ourselves.
MAX_PAYLOAD_AGE_S = 3600
# Supervisor cadence. Faster while there is nothing to serve at all.
TICK_EMPTY_S = 120
TICK_IDLE_S = 300


def _payload_age_s(p: dict | None) -> float | None:
    if not p:
        return None
    try:
        return (pd.Timestamp.utcnow() - pd.Timestamp(p["generated_at"])).total_seconds()
    except (KeyError, ValueError):
        return None


def cron_is_healthy() -> bool:
    """Has the refresh cron reported a run recently?

    refresh_job.run() writes this on every run, success or failure, so a cron
    that is alive but failing still counts as present — it owns the retry, and a
    second rebuilder racing it would not help.
    """
    meta = kv.get_json(kv.FORECAST_META_KEY)
    if not meta or not meta.get("ran_at"):
        return False
    try:
        age = (pd.Timestamp.utcnow() - pd.Timestamp(meta["ran_at"])).total_seconds()
    except ValueError:
        return False
    return 0 <= age <= CRON_GRACE_S


def refresher() -> str:
    """Which process is actually keeping the forecast current."""
    return "cron" if cron_is_healthy() else "web-fallback"


def _supervise_once() -> None:
    """Rebuild the forecast if, and only if, nothing else is going to.

    The steady state on Render is the cron job, and in that state this does
    nothing at all — which is what keeps LightGBM out of this process, since the
    heavy imports live inside cache._build_payload().

    It exists because a web service that only ever reads is helpless when nothing
    is writing. With no cron and no Key Value the old one-shot warm-up left the
    forecast frozen at whatever the cold start produced, ageing silently forever.
    """
    if cron_is_healthy():
        return
    age = _payload_age_s(cache.get())
    if age is not None and age <= MAX_PAYLOAD_AGE_S:
        return
    why = "no forecast" if age is None else f"forecast {round(age / 60)} min old"
    print(f"[supervisor] no cron refreshing ({why}) - rebuilding here")
    cache.refresh()


def _supervisor():
    while True:
        try:
            _supervise_once()
        except Exception as e:  # noqa: BLE001 - this thread must outlive any failure
            print(f"[supervisor] tick failed: {type(e).__name__}: {e}")
        time.sleep(TICK_EMPTY_S if cache.get() is None else TICK_IDLE_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[boot] cache backend: {kv.backend()}, refresher: {refresher()}")
    threading.Thread(target=_supervisor, daemon=True).start()
    yield


app = FastAPI(title="Loadshift API", lifespan=lifespan)

# On Render the browser reaches this service through the Next.js rewrite in
# loadshift-web, same-origin, so no CORS is involved at all. The wildcard is
# for the Vercel fallback deployment and local dev; every endpoint is public,
# read-only, and unauthenticated, so there is no cookie or session to protect.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def _payload() -> dict:
    p = cache.get()
    if not p:
        raise HTTPException(503, "forecast cache warming up — try again in a minute")
    return p


# The insight endpoints take the stats back from the client, so bound them: a
# prompt is built from this and we pay for every token of it. A real analysis
# serialises to ~1.3 KB (measured on the bundled sample), so this is 3x headroom
# rather than the 15x it was — the endpoint accepts client input and every byte
# above is billable.
MAX_STATS_BYTES = 4_000


def _check_stats(stats: dict) -> None:
    try:
        blob = json.dumps(stats, default=str)
    except (TypeError, ValueError) as e:
        raise HTTPException(422, "stats must be JSON-serializable") from e
    if len(blob) > MAX_STATS_BYTES:
        raise HTTPException(422, "stats payload too large")


def _client(request: Request) -> str:
    """Caller identity for the shared-key budget. Render sets X-Forwarded-For;
    its first hop is the original client."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limited(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "You have used the questions available on the shared key. "
                      "Add your own Gemini key to keep going.",
            "reason": "rate_limited",
            "remaining": 0,
        },
        headers={"Retry-After": str(retry_after)},
    )


def _failed(e: insights.InsightsError, remaining: int | None) -> JSONResponse:
    """A spent quota is not the same as a broken upstream; say which."""
    quota = e.reason == "quota"
    return JSONResponse(
        status_code=429 if quota else 503,
        content={
            "detail": "The shared key is out of quota for now. Add your own "
                      "Gemini key to keep going."
            if quota
            else "Insights are unavailable right now.",
            "reason": e.reason,
            "remaining": remaining,
        },
    )


def _cache_age_s(p: dict | None) -> int | None:
    if not p:
        return None
    age = (pd.Timestamp.utcnow() - pd.Timestamp(p["generated_at"])).total_seconds()
    return round(age)


@app.get("/api/health")
def health():
    """Liveness. Always 200 on purpose — this is Render's healthCheckPath, and
    a warming instance must not fail its own deploy. Readiness is /api/ready."""
    p = cache.get()
    return {
        "ok": True,
        "artifacts_loaded": (config.ARTIFACTS / "model.txt").exists(),
        "cache_age_s": _cache_age_s(p),
        "stale": p["stale"] if p else None,
        # Which weather a served forecast was actually built from: a payload
        # standing on a stored snapshot should be visible without guessing.
        "weather_source": p.get("weather_source") if p else None,
        "weather_age_h": p.get("weather_age_h") if p else None,
        # Which tier answered. "in-process (kv unreachable)" means the durable
        # cache is down and this instance is running on whatever it still holds.
        "cache_backend": kv.backend(),
        "kv_ok": kv.available(),
        "kv_error": kv.last_error(),
        # "web-fallback" means no cron has reported in and this process is
        # rebuilding the forecast itself. Serving correctly, wrong topology.
        "refresher": refresher(),
        **cache.diagnostics(),
    }


@app.get("/api/ready")
def ready():
    """Readiness: can this instance actually answer /api/forecast right now?

    Deliberately NOT wired to healthCheckPath — Render would fail the deploy of
    an instance that is merely waiting on its first cron run.
    """
    p = cache.get()
    body = {
        "ready": p is not None,
        "cache_age_s": _cache_age_s(p),
        "cache_backend": kv.backend(),
        **cache.diagnostics(),
    }
    return JSONResponse(status_code=200 if p else 503, content=body)


@app.get("/api/platform")
def platform():
    """Where this response came from, and who built the forecast in it.

    Render injects the service/commit/instance identifiers; the refresh block
    is written by the cron job. Surfaced in the UI footer so the deployment
    topology is inspectable rather than asserted.
    """
    meta = kv.get_json(kv.FORECAST_META_KEY) or {}
    p = cache.get()
    return {
        "platform": "render" if os.environ.get("RENDER") else "local",
        "service": os.environ.get("RENDER_SERVICE_NAME"),
        "service_type": os.environ.get("RENDER_SERVICE_TYPE"),
        "instance": os.environ.get("RENDER_INSTANCE_ID"),
        "commit": (os.environ.get("RENDER_GIT_COMMIT") or "")[:7] or None,
        "branch": os.environ.get("RENDER_GIT_BRANCH"),
        "is_preview": os.environ.get("IS_PULL_REQUEST") == "true",
        "cache_backend": kv.backend(),
        "cache_age_s": _cache_age_s(p),
        "refresher": refresher(),
        "refresh": {
            "by_service": meta.get("service"),
            "by_commit": meta.get("commit"),
            "ran_at": meta.get("ran_at"),
            "ok": meta.get("ok"),
            "duration_s": meta.get("duration_s"),
            "generated_at": meta.get("generated_at"),
            "weather_source": meta.get("weather_source"),
        },
    }


@app.get("/api/now")
def now():
    p = _payload()
    return {**p["now"], "stale": p["stale"], "generated_at": p["generated_at"]}


@app.get("/api/forecast")
def forecast():
    return _payload()


class ScheduleReq(BaseModel):
    appliance: str | None = None       # key into APPLIANCE_DEFAULTS
    kwh: float | None = None           # exact energy per run, overrides range
    watts: float | None = None         # nameplate power, overrides range
    duration_h: int = 1
    awake_start: int | None = None     # local hour you wake (0-23)
    awake_end: int | None = None       # local hour you go to bed (0-23)


@app.post("/api/schedule")
def schedule(req: ScheduleReq):
    try:
        series = cache.forecast_series()
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e

    duration = req.duration_h
    if req.appliance and req.appliance in config.APPLIANCE_DEFAULTS:
        d = config.APPLIANCE_DEFAULTS[req.appliance]
        kwh_range = tuple(d["kwh_range"])
        duration = req.duration_h or d["duration_h"]
    else:
        kwh_range = (1.0, 1.0)
    if req.watts:
        kwh = req.watts / 1000 * duration
        kwh_range = (kwh, kwh)
    elif req.kwh:
        kwh_range = (req.kwh, req.kwh)

    def window_payload(res: dict) -> dict:
        lo, hi = optimize.grams_saved(res, kwh_range)
        kwh_mid = sum(kwh_range) / 2
        cost_best = pricing.window_cost_cents(kwh_mid, res["best_start"], duration)
        cost_worst = pricing.window_cost_cents(kwh_mid, res["worst_start"], duration)
        cost_best_ulo = pricing.window_cost_cents(kwh_mid, res["best_start"], duration, "ulo")
        return {
            "best_start": res["best_start"].isoformat() + "Z",
            "best_gco2_kwh": res["best_gco2_kwh"],
            "worst_start": res["worst_start"].isoformat() + "Z",
            "worst_gco2_kwh": res["worst_gco2_kwh"],
            "pct_saving": res["pct_saving"],
            "g_saved_range": [lo, hi],
            "cost_best_cents": cost_best,
            "cost_worst_cents": cost_worst,
            "cents_saved": round(cost_worst - cost_best, 1),
            "cost_best_ulo_cents": cost_best_ulo,
        }

    try:
        overall = optimize.best_window(series, duration)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    # Awake constraint: a run must START while you're up (it may finish while
    # you sleep). Wraparound handled for night-shift schedules.
    constrained = None
    awake = None
    if req.awake_start is not None and req.awake_end is not None             and req.awake_start != req.awake_end:
        w, b = req.awake_start % 24, req.awake_end % 24
        local_h = (
            series.index.tz_localize("UTC")
            .tz_convert(config.TIMEZONE)
            .hour
        )
        mask = (local_h >= w) & (local_h < b) if w < b else (local_h >= w) | (local_h < b)
        try:
            constrained = window_payload(
                optimize.best_window(series, duration, allowed_starts=series.index[mask])
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        awake = [w, b]

    return {
        "overall": window_payload(overall),
        "constrained": constrained,
        "awake": awake,
        "kwh_range": list(kwh_range),
        "duration_h": duration,
        "stale": _payload()["stale"],
    }


@app.post("/api/greenbutton")
async def greenbutton_upload(file: UploadFile = File(...)):
    data = await file.read()
    try:
        stats = greenbutton.analyze(greenbutton.parse(data))
    except (ValueError, ET_ParseError) as e:
        raise HTTPException(422, f"could not analyze file: {e}") from e
    # No AI call here: generation takes ~20s and the numbers must not wait on it.
    return {**stats, "ai_available": insights.available()}


@app.get("/api/greenbutton/sample")
def greenbutton_sample():
    kwh = greenbutton.parse(greenbutton.SAMPLE_PATH.read_bytes())
    stats = greenbutton.analyze(kwh)
    return {**stats, "sample": True, "ai_available": insights.available()}


class StatsReq(BaseModel):
    stats: dict


@app.post("/api/insights/report")
def insights_report(
    req: StatsReq,
    request: Request,
    x_gemini_key: str | None = Header(default=None),
):
    _check_stats(req.stats)
    own = bool(x_gemini_key)
    client = _client(request)

    # A cache hit costs no quota, so it must not cost the visitor an allowance.
    hit = insights.cached_report(req.stats)
    if hit is not None:
        return {**hit, "remaining": None if own else ratelimit.shared.remaining(client)}

    if not own:
        ok, _, retry = ratelimit.shared.check(client)
        if not ok:
            return _limited(retry)
    try:
        rep = insights.report(req.stats, user_key=x_gemini_key)
    except insights.InsightsError as e:
        return _failed(e, None if own else ratelimit.shared.remaining(client))
    remaining = None if own else ratelimit.shared.consume(client)
    return {**rep, "remaining": remaining}


class AskReq(BaseModel):
    question: str
    stats: dict


@app.post("/api/insights/ask")
def insights_ask(
    req: AskReq,
    request: Request,
    x_gemini_key: str | None = Header(default=None),
):
    q = req.question.strip()
    if not q or len(q) > 300:
        raise HTTPException(422, "question must be 1-300 characters")
    _check_stats(req.stats)
    own = bool(x_gemini_key)
    client = _client(request)

    hit = insights.cached_ask(q, req.stats)
    if hit is not None:
        return {
            "answer": hit,
            "model": insights.MODEL,
            "remaining": None if own else ratelimit.shared.remaining(client),
        }

    if not own:
        ok, _, retry = ratelimit.shared.check(client)
        if not ok:
            return _limited(retry)
    try:
        answer = insights.ask(q, req.stats, user_key=x_gemini_key)
    except insights.InsightsError as e:
        return _failed(e, None if own else ratelimit.shared.remaining(client))
    remaining = None if own else ratelimit.shared.consume(client)
    return {"answer": answer, "model": insights.MODEL, "remaining": remaining}


@app.get("/api/model-card")
def model_card():
    card = json.loads((config.ARTIFACTS / "model_card.json").read_text())
    curve = json.loads((config.ARTIFACTS / "mef_curve.json").read_text())
    slopes = [s for c in curve["curves"].values() for s in c["sum_slope"]]
    card["mef_method"] = {
        "method": curve["method"],
        "citation": curve["citation"],
        "mean_sum_slope": round(sum(slopes) / len(slopes), 2),
        "note": "sum_slope < 1 means part of the marginal response is served "
                "by intertie flows we do not model — a stated limitation",
    }
    return card

