"""Loadshift API. Serves cached forecasts only — no model runs on request paths."""
from __future__ import annotations

import json
import threading
from contextlib import asynccontextmanager
from xml.etree.ElementTree import ParseError as ET_ParseError

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import (
    cache, config, greenbutton, insights, model, optimize, pricing, ratelimit,
)


def _boot_refresh():
    """Refresh until the first success: a fresh instance has no cache to
    serve stale, and upstream rate limits (Open-Meteo 429 after repeated
    deploys) must not leave the site empty for the next hourly tick."""
    import time as _time

    while not cache.refresh():
        _time.sleep(120)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Retry-until-first-success in a thread so boot isn't blocked; hourly after.
    threading.Thread(target=_boot_refresh, daemon=True).start()
    sched = BackgroundScheduler()
    sched.add_job(cache.refresh, "interval", minutes=60, id="refresh")
    sched.start()
    yield
    sched.shutdown(wait=False)


app = FastAPI(title="Loadshift API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def _payload() -> dict:
    p = cache.get()
    if not p:
        raise HTTPException(503, "forecast cache warming up — try again in a minute")
    return p


# The insight endpoints take the stats back from the client, so bound them: a
# prompt is built from this and we pay for every token of it.
MAX_STATS_BYTES = 20_000


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


@app.get("/api/health")
def health():
    p = cache.get()
    age = None
    if p:
        age = (pd.Timestamp.utcnow() - pd.Timestamp(p["generated_at"])).total_seconds()
    return {
        "ok": True,
        "artifacts_loaded": (model.ARTIFACTS / "model.txt").exists(),
        "cache_age_s": round(age) if age is not None else None,
        "stale": p["stale"] if p else None,
        **cache.diagnostics(),
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
    card = json.loads((model.ARTIFACTS / "model_card.json").read_text())
    curve = json.loads((model.ARTIFACTS / "mef_curve.json").read_text())
    slopes = [s for c in curve["curves"].values() for s in c["sum_slope"]]
    card["mef_method"] = {
        "method": curve["method"],
        "citation": curve["citation"],
        "mean_sum_slope": round(sum(slopes) / len(slopes), 2),
        "note": "sum_slope < 1 means part of the marginal response is served "
                "by intertie flows we do not model — a stated limitation",
    }
    return card

