# Grid-Aware Appliance Scheduler — Ignition Hacks V.7

**Track:** Environmental
**Window:** Hacking 8:00 PM Sat → 6:00 PM Sun (22h). Judging 6–8 PM. Closing 8–9 PM.

---

## 1. The pitch

Ontario's grid looks clean on paper — mostly nuclear and hydro, average intensity around 30–60 gCO₂eq/kWh. So why schedule anything?

Because **average intensity is the wrong number.** Nuclear runs flat regardless of demand. When you add one more kWh of load, the plant that ramps to serve it is almost always natural gas. The emissions *caused by your dryer* are near gas intensity (~400–500 gCO₂/kWh), not the ~40 g average.

We forecast Ontario's **marginal** carbon intensity 24 hours ahead and tell you the cheapest hour, in CO₂ terms, to run a deferrable load.

**One-line version:** "Your dryer doesn't emit the grid average. It emits whatever turned on because of it."

---

## 2. Why this wins

| Judging axis | Our answer |
|---|---|
| Technical depth | Real time-series forecasting, benchmarked against a stated baseline |
| Originality | Marginal vs. average is a genuine insight most teams miss |
| Data | Live public grid data, not mocked |
| Demo | Live Ontario grid on screen at judging time |
| Local relevance | Ontario grid, Ontario regulation, our own meter data |
| Feasibility | Every stage independently demoable |

---

## 3. Data sources — all free, no paid keys

### IESO Public Reports (primary)
- Host: `https://reports-public.ieso.ca/public/`
  - Older docs reference `reports.ieso.ca` — use the `reports-public` host.
- Flat HTTPS file repository. Anonymous access, no API key, no registration.
- URL pattern: `/public/<DocID>/PUB_<Report>_<YYYYMMDD>_v<n>.<ext>`
- **Filename with no date suffix always = most recent version.** That's the live feed.
- Reports we need:
  - `GenOutputbyFuelHourly/` — historical hourly generation by fuel type (training data)
  - `GenOutputCapability/PUB_GenOutputCapability.xml` — live per-generator output
  - Hourly Ontario demand

**Trap:** the XML namespace for `GenOutputCapability` is `http://www.theIMO.com/schema` and differs from IESO's other files. Budget for this or lose 20 minutes.

**Trap:** IESO went through a Market Renewal — some older library methods and report formats are retired. Verify any tutorial code against a live fetch before trusting it.

### Open-Meteo (weather features)
- Free, no API key. Serves **both** historical archive and forecast — essential, since you train on history and infer on forecast.
- Features: temperature, wind speed, cloud cover, solar radiation.

### Electricity Maps free tier (validation only)
- Hourly carbon intensity in gCO₂eq/kWh. Free tier is limited to a single zone.
- **Do not build on this.** Use it once, to sanity-check our numbers. "Our average-intensity calculation tracks Electricity Maps within X g/kWh" is a strong credibility line in the video.

### Green Button (the differentiator)
- Ontario Regulation 633/21; rate-regulated utilities required to provide access since Nov 1, 2023.
- Customers download up to 24 months of smart-meter interval data as standardized XML.
- Alectra covers Mississauga → **demo with our own household data.**
- Feature: upload your Green Button XML → we compute your actual emissions vs. optimally-scheduled emissions over the past year.

---

## 4. The household variance problem — and the fix

**The concern:** appliances differ hugely between homes, so any savings figure is guesswork.

**The resolution:** percentage savings is independent of appliance size.

```
Absolute savings = E × (I_peak − I_off)     ← scales with E, varies by household
Percent savings  = (I_peak − I_off) / I_peak ← E cancels; grid-determined only
```

The percentage is identical for a 0.9 kWh efficient dryer and a 5 kWh ancient one. It depends *only* on the grid, which is exactly what we forecast.

**Therefore:** headline the percentage. Treat grams as secondary and caveated.

Three tiers for the absolute number:

1. **Default** — NRCan EnerGuide typical values, shown as a **range** ("180–420 g saved"). A range reads as rigour; a fake-precise point estimate reads as naive.
2. **Nameplate input** — user types watts off the appliance sticker. Exact for their unit.
3. **Green Button upload** — real metered data, zero assumptions.

**Put this limitation on a slide explicitly.** Naming your own weakness before a judge does is worth more than hiding it.

---

## 5. Method

### Labelling marginal intensity (the hard part)
Simplest defensible rule:
- Per hour, check whether gas fleet output moved with demand.
- If gas is on the margin → marginal intensity ≈ gas fleet intensity.
- If not → fall back to a stated alternative.

**Document the assumption openly in the README and the video.** Judges respect a stated simplification far more than a hidden one. Do not silently pass average intensity off as marginal.

### Forecasting
- Model: LightGBM (or XGBoost), 24h-ahead marginal intensity.
- Features: hour-of-day, day-of-week, month, temperature, wind speed, cloud cover, lagged demand, lagged intensity.
- **Build the seasonal-naive baseline FIRST** ("same hour last week"). Report MAE improvement over it.
- A stated MAE against a real baseline outweighs any amount of frontend polish.

### Optimizing
Given appliance kWh + run duration, sliding-window argmin over the 24h forecast. This is a few lines. Do not over-engineer it.

---

## 6. Hour-by-hour

| Time | Task | Ship gate |
|---|---|---|
| 8–10 PM | Ingest. Parse one XML end-to-end before writing anything else. Pull 2–3 yrs fuel mix + demand. | Raw data in a DataFrame |
| 10 PM–12 AM | Join weather. Label marginal intensity. | Labelled training set |
| 12–2 AM | Baseline + LightGBM. Backtest. | MAE beats baseline |
| **2–6 AM** | **SLEEP (rotate shifts).** Non-negotiable. | — |
| 6–8 AM | FastAPI backend. Cached forecast endpoint. | `/forecast` returns JSON |
| 8 AM–12 PM | Frontend: live gauge, 24h curve, scheduler, Green Button upload. | Clickable demo |
| 12–2 PM | Deploy to Render. Green Button end-to-end with real data. | Public URL works |
| **2 PM** | **FEATURE FREEZE.** No new code paths. | — |
| 2–4 PM | Record video. Write README. | Video uploaded |
| 4–6 PM | Rehearse. Buffer for disaster. | — |
| 6 PM | Hard stop. | — |

**Sleep 2–6 AM.** Teams lose on incoherent 6 PM presentations far more often than on missing features.

**Schedule conflicts:** Base44 workshop 1:45–2:30 PM sits on the freeze deadline. Waterloo panel at noon sits mid-frontend. Skip both if behind, attend if ahead. skribbl.io minigame 10–11 PM — skip, that's peak ingest time.

---

## 7. Deliverables

### Deployed site
- **Render free tier spins down when idle.** A judge clicking hours later waits ~50s and leaves. We have $50 Render credits — use a paid instance through judging.
- **Never let a page load trigger a live model run.** Cron the forecast, serve cached JSON.
- If IESO fails mid-judging, serve last-known-good with a visible timestamp. Never show an error page.
- Include a "Try sample data" button — judges will not have their own Green Button file.

### Video (2–3 min, unlisted YouTube)
| Time | Beat |
|---|---|
| 0:00–0:20 | Hook: "Ontario's grid is 90% clean. So why does when you run your dryer matter?" |
| 0:20–0:50 | The marginal vs. average insight. This is the core — do not rush it. |
| 0:50–2:00 | Live demo. Real screen recording, real data, no slides. |
| 2:00–2:30 | Technical depth: model, MAE vs. baseline, validation against Electricity Maps. |
| 2:30–2:50 | Green Button on our own house. Limitations stated. |
| 2:50–3:00 | Close + URL. |

- Record with OBS. **Narrate it yourself** — authentic voice generally lands better with judges than synthesized narration for a project pitch.
- **Record a backup demo take** in case live data misbehaves during judging.
- Put the URL in the video description and on the final frame.

### README
Problem → insight → data sources → method → **stated assumptions and limitations** → run instructions.

---

## 8. Pre-8 PM checklist

- [ ] Confirm submission format and deadline (Devpost? Discord?) — the package doesn't specify
- [ ] Email World Labs — codes go to first 50 teams, costs 5 minutes, keeps an option open
- [ ] Register Electricity Maps free tier key
- [ ] **Download your own Green Button XML from Alectra now** — portal auth may be slow, do not discover this at 3 AM
- [ ] Test-fetch one IESO XML and confirm it parses
- [ ] Create Render account, verify deploy works with a hello-world
- [ ] Redeem sponsor codes (Base44 `50AU700`, Mobbin `IGNITIONHACKS`, n8n `2026-COMMUNITY-HACKATHON-TORONTO-2B7C2514`)

---

## 9. Risk register

| Risk | Mitigation |
|---|---|
| "Isn't Ontario already clean?" | Marginal vs. average. Rehearse this answer cold. |
| Marginal labelling eats hours | Timebox to 2h. Fall back to average intensity, clearly relabelled. |
| Model doesn't beat baseline | Report it honestly. Still a working product; honesty scores better than a fudged metric. |
| IESO down during judging | Cached last-known-good + timestamp. |
| Render cold start | Paid instance during judging window. |
| Green Button auth fails | Have the XML downloaded before 8 PM. |
| Scope creep | 2 PM freeze is absolute. |
