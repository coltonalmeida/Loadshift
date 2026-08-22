"""Loadshift API. Serves cached forecasts only — no model runs on request paths."""
from __future__ import annotations

import json
import threading
from contextlib import asynccontextmanager
from xml.etree.ElementTree import ParseError as ET_ParseError

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import cache, config, greenbutton, insights, model, optimize, pricing


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
    return {**stats, "ai_report": insights.report(stats)}


@app.get("/api/greenbutton/sample")
def greenbutton_sample():
    kwh = greenbutton.parse(greenbutton.SAMPLE_PATH.read_bytes())
    stats = greenbutton.analyze(kwh)
    return {**stats, "sample": True, "ai_report": insights.report(stats)}


class AskReq(BaseModel):
    question: str
    stats: dict


@app.post("/api/insights/ask")
def insights_ask(req: AskReq):
    q = req.question.strip()
    if not q or len(q) > 300:
        raise HTTPException(422, "question must be 1-300 characters")
    answer = insights.ask(q, req.stats)
    if answer is None:
        raise HTTPException(503, "insights are unavailable right now")
    return {"answer": answer.strip(), "model": insights.MODEL}


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

