# Stated assumptions and limitations

Every simplification in Loadshift, in one place. We would rather name these than
have you find them.

## Marginal intensity labelling

1. **Intertie flows are not modelled.** Our fuel-slope regression explains on
   average ~78% of a marginal Ontario kWh (`mean_sum_slope` in the model card);
   the remainder is served by imports/exports whose emissions we do not observe.
   At extreme peaks the true marginal unit may be an out-of-province plant.
2. **Up-deltas only.** We regress on hours where demand *rose*, because the
   product question is "what turns on for an added kWh". Down-ramps behave
   differently (gas tracks demand downward overnight) and are excluded.
3. **Bucketed, not unit-level.** Marginal response is estimated per
   season x hour-block bucket, conditioned on net demand — not per generator.
   Sparse buckets (few up-deltas, e.g. evening rampdown) fall back to a single
   whole-bucket estimate.
4. **Emission factors are IPCC AR5 lifecycle medians.** A specific Ontario CCGT
   may differ from the 490 g default; we do not model per-plant heat rates.

## Forecasting

5. **The 80% confidence band is ±1.28 × holdout MAE**, an empirical error
   band, not a per-hour predictive distribution.
6. **The "average" line in the forecast chart is same-hour-yesterday**, a
   seasonal naive estimate shown for comparison only. The marginal line is the
   actual model output.

## Live data

7. **IESO yearly files update daily.** We extend to the current hour with the
   hourly GenOutputCapability feed; for those hours Ontario demand is estimated
   as total generation × the trailing 7-day demand/generation ratio (Ontario is
   a net exporter, so generation > demand). Flagged as `demand_estimated`.
8. **IESO reports use fixed Eastern Standard Time year-round** (verified: DST
   transition days have exactly 24 rows). All joins are done in UTC.
9. **A single missing hour** (2025-05-01 05:00 UTC, IESO Market Renewal
   go-live) is linearly interpolated.

## Savings figures

10. **Percent savings is the headline because it is appliance-independent** —
    the kWh cancels. Absolute grams use NRCan EnerGuide typical ranges unless
    you enter nameplate watts or upload Green Button data.
11. **Green Button "if shifted" assumes 30% of each day's load is deferrable**
    and moves into that day's cleanest 4-hour window. Your deferrable share
    may differ; the assumption is printed next to every result.
12. **The bundled sample file is synthetic** (a realistic Ontario household
    profile) so the demo works without anyone's personal meter data.
