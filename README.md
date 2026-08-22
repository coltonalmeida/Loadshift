# Loadshift

**Your dryer doesn't emit the grid average. It emits whatever turned on because
of it.**

Ontario's grid averages a very clean ~100 gCO₂eq/kWh — mostly nuclear and hydro.
But nuclear runs flat regardless of demand. Add one more kWh of load and the
plant that ramps to serve it is almost always natural gas at ~490 g. The
emissions *caused by your appliance* are the **marginal** intensity, not the
average — and unlike the average, the marginal intensity swings ~50% within a
typical day.

Loadshift forecasts Ontario's marginal carbon intensity 24 hours ahead and names
the cleanest hour to run a deferrable load.

Built solo at Ignition Hacks V.7 (Environmental track).

## How it works

1. **Ingest** — 2.6 years of hourly generation-by-fuel and demand from
   [IESO Public Reports](https://reports-public.ieso.ca/public/) (no key
   required), joined with Open-Meteo weather. All in UTC (IESO reports use fixed
   EST year-round — verified against DST transition days).
2. **Label** — marginal emissions factor per Siler-Evans, Azevedo & Morgan
   (2012, *Environ. Sci. Technol.* 46(9)): regress each fuel's hourly ramp on
   demand ramps, per season × hour-block, conditioned on net demand
   (demand − wind − solar), using demand-*increase* hours only. MEF =
   Σ(slope_fuel × EF_fuel) with IPCC AR5 lifecycle factors.
3. **Forecast** — LightGBM, 24h ahead. Every feature is causal at that horizon
   (calendar, forecast weather, lags ≥ 24h). Chronological 60-day holdout:
   **MAE 13.5 g vs 23.2 g for the seasonal-naive baseline — 42% better.**
4. **Optimize** — sliding-window argmin over the forecast for your appliance's
   duration. Percent savings is appliance-independent (the kWh cancels), so
   that is the headline number.
5. **Green Button** — upload your own smart-meter XML (every Ontario utility
   must provide it under O. Reg. 633/21) and see what shifting would have saved
   you over the past year. A synthetic sample file is bundled.

**External validation:** our independently-computed average intensity tracks
Electricity Maps' Ontario figure within **2.1 g/kWh** (bias +1.8 g, correlation
0.91) over the overlapping window — same lifecycle emission-factor basis. We
validate against their API once; we do not build on it.

Assumptions and limitations are stated in [ASSUMPTIONS.md](ASSUMPTIONS.md) —
including the big one: intertie flows are unmodelled, and our slopes explain
~78% of a marginal kWh.

## Architecture

All heavy work happens locally and produces small committed artifacts
(`api/artifacts/`). The server never trains and never parses a year of XML.

The deployment is four Render resources in one Blueprint ([`render.yaml`](render.yaml)):

```
browser ─▶ loadshift-web   (Next.js + Recharts)   public URL; proxies /api/*
                │                                  over Render's private network
                ▼
           loadshift-api   (FastAPI)              reads the cache; never the model
                │
                ▼
           loadshift-cache (Key Value)            the only tier that survives a deploy
                ▲
                │
           loadshift-refresh (cron, hourly)       the only process that runs LightGBM
```

A page load never triggers a forecast rebuild. The cron job publishes a fresh
forecast to Key Value each hour and the web service only reads it, so "never run
the model on a request path" is a property of the topology rather than a
convention — the web service does not import LightGBM at all. If an upstream
feed fails, the last-known-good forecast keeps being served with a visible
`stale` flag and the timestamp it was built.

Endpoints: `/api/forecast` `/api/now` `/api/schedule` `/api/greenbutton`
`/api/model-card` `/api/health` `/api/ready` `/api/platform`

See [DEPLOY.md](DEPLOY.md) for why the split exists and how it degrades.

## Run it

Nothing here needs Render. `KV_URL` is unset locally, so the app falls back to
its in-process and on-disk caches.

```bash
# backend (Python 3.12)
python -m venv .venv && .venv/Scripts/pip install -r api/requirements-dev.txt
cd api
../.venv/Scripts/python scripts/smoke_sources.py    # verify upstreams
../.venv/Scripts/python scripts/build_dataset.py    # ~2 min, cached downloads
../.venv/Scripts/python scripts/fit_mef.py
../.venv/Scripts/python scripts/train.py
../.venv/Scripts/python -m loadshift.refresh_job    # one forecast rebuild
../.venv/Scripts/python -m uvicorn loadshift.main:app --port 8000

# frontend
cd web && npm install && npm run dev                # NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Tests: `cd api && ../.venv/Scripts/python -m pytest tests/ -q`

`requirements.txt` is what Render installs; `requirements-dev.txt` adds pytest on
top of it.

## Data sources

- IESO Public Reports — generation by fuel, demand, live generator output
- Open-Meteo — historical + forecast weather (no key)
- Green Button (O. Reg. 633/21) — customer smart-meter interval data
- Emission factors — IPCC AR5 WGIII Annex III lifecycle medians
