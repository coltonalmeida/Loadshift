"use client";
import { useEffect, useState } from "react";
import { fetchModelCard, ModelCard } from "@/lib/api";

export default function MethodSection() {
  const [card, setCard] = useState<ModelCard | null>(null);

  useEffect(() => {
    fetchModelCard().then(setCard).catch(() => {});
  }, []);

  return (
    <div>
      <div>
        <h2 className="display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          How we get these numbers
        </h2>
        <p className="mt-3 max-w-[62ch] leading-relaxed text-ink-2">
          Average intensity tells you what the whole grid emitted. Marginal
          intensity tells you what turned on because of one more kilowatt hour.
          In Ontario that is usually a natural gas plant, so the marginal number
          runs far above the average, and it swings within a day. We measure it,
          then forecast it.
        </p>
      </div>

      {card && (
        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            { label: "Forecast error", value: `${card.mae_model} g`, sub: "MAE, 60-day holdout" },
            { label: "Naive baseline", value: `${card.mae_baseline_seasonal_naive_168h} g`, sub: "same hour last week" },
            { label: "Improvement", value: `${card.improvement_pct}%`, sub: "over the baseline", accent: true },
            { label: "Test R²", value: `${card.test_r2}`, sub: "chronological split" },
          ].map((s) => (
            <div key={s.label} className="rounded-xl border border-line bg-surface p-5">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-3">
                {s.label}
              </div>
              <div className={`mono mt-1 text-2xl ${s.accent ? "text-spruce-deep" : "text-ink"}`}>
                {s.value}
              </div>
              <div className="mt-0.5 text-[11px] text-ink-3">{s.sub}</div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-10 grid gap-8 lg:grid-cols-2">
        <div className="space-y-4 text-sm leading-relaxed text-ink-2">
          <h3 className="display text-xl font-bold tracking-tight text-ink">
            Measuring the margin
          </h3>
          <p>
            For every hour when Ontario demand rose, we ask which fuels rose
            with it. A regression of each fuel&rsquo;s ramp against the demand
            ramp (per season and time of day, conditioned on net demand) gives
            the marginal mix, and pairing it with lifecycle emission factors
            gives grams per kilowatt hour. The method follows Siler-Evans,
            Azevedo and Morgan (2012), <em>Environmental Science &amp;
            Technology</em> 46(9).
          </p>
          <p>
            The forecast is machine learning end to end: LightGBM
            gradient-boosted decision trees trained on roughly 23,000 hours
            (2.6 years) of IESO grid history, using 14 features across
            calendar, forecast weather, and day-old lags, so every input is
            genuinely available 24 hours ahead. It is validated on a
            chronological 60-day holdout against an honest baseline,
            &ldquo;same hour last week,&rdquo; and beats it by 42%.
          </p>
          <p>
            Dollar figures use the OEB regulated Time-of-Use and Ultra-Low
            Overnight rate schedules effective November 2025, applied hour by
            hour to the same windows the carbon optimizer picks. In Ontario the
            cheap hours and the clean hours largely coincide overnight, which
            is why one shift pays twice.
          </p>
          <p>
            As a sanity check, our independently computed average intensity
            tracks Electricity Maps&rsquo; Ontario figure within 2.1 g/kWh
            (correlation 0.91) on the same lifecycle basis.
          </p>
        </div>

        <div className="space-y-4">
          {card && (
            <div className="rounded-xl border border-line bg-surface p-5">
              <h3 className="mb-3 text-sm font-medium text-ink">
                Lifecycle emission factors (IPCC AR5), g CO₂eq/kWh
              </h3>
              <div className="grid grid-cols-3 gap-x-4 gap-y-2">
                {Object.entries(card.emission_factors_gco2_kwh)
                  .sort((a, b) => b[1] - a[1])
                  .map(([fuel, ef]) => (
                    <div key={fuel} className="flex items-baseline justify-between gap-2">
                      <span className="text-xs text-ink-2">{fuel.toLowerCase()}</span>
                      <span className="mono text-sm text-ink">{ef}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {card && (
            <div className="rounded-xl border border-amber/30 bg-surface p-5 text-sm leading-relaxed text-ink-2">
              <span className="font-medium text-amber">Known limitation:</span>{" "}
              only about {Math.round(card.mef_method.mean_sum_slope * 100)}% of a
              marginal Ontario kilowatt hour is explained by the fuels we model.
              The rest flows through interties whose emissions we do not
              observe. Every other simplification is listed in{" "}
              <a
                className="underline decoration-line underline-offset-2 hover:text-ink"
                href="https://github.com/coltonalmeida/Loadshift/blob/main/ASSUMPTIONS.md"
              >
                ASSUMPTIONS.md
              </a>
              .
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
