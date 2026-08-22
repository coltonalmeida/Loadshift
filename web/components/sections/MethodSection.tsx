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
          Average intensity tells you what the whole grid emitted overall.
          Marginal intensity tells you which power plant had to ramp up extra
          output to supply the next kilowatt-hour of demand across the system.
          In Ontario that extra power usually comes from a natural gas plant, so
          the marginal number runs far above the average, and it swings within a
          day. We measure it, then forecast it.
        </p>
      </div>

      {card && (
        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            { label: "Forecast error", value: `${card.mae_model} g`, sub: "Average grams of CO₂ our model was off by" },
            { label: "Naive baseline", value: `${card.mae_baseline_seasonal_naive_168h} g`, sub: "Error if we just guessed using last week\u2019s data" },
            { label: "Improvement", value: `${card.improvement_pct}%`, sub: "Accuracy gained compared to the simple guess", accent: true },
            { label: "Test R²", value: `${card.test_r2}`, sub: "Overall model accuracy score" },
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
            Every hour, Ontario&rsquo;s electricity demand rises or falls. We
            look at which power plants moved with it — when the province
            needed more power, who actually produced it? Doing that across
            years of hourly data, separately for each season and time of day,
            shows which fuels answer the next kilowatt-hour. Multiply that mix
            by how much CO₂ each fuel emits over its lifetime and you get
            grams per kilowatt-hour. This is the standard method, from
            Siler-Evans, Azevedo and Morgan (2012), <em>Environmental Science
            &amp; Technology</em> 46(9).
          </p>
          <p>
            To predict tomorrow, we train a machine learning model —
            LightGBM, a decision-tree ensemble — on about 23,000 hours
            (2.6 years) of Ontario grid history. It reads 14 inputs: the
            calendar, the weather forecast, and grid readings from a day
            earlier, so nothing it needs is unavailable 24 hours ahead. We test
            it on 60 days it never saw during training, against a fair
            benchmark — just guessing &ldquo;whatever it was this hour last
            week&rdquo; — and it beats that guess by 42%.
          </p>
          <p>
            The dollar savings use Ontario&rsquo;s official electricity prices
            — the OEB&rsquo;s Time-of-Use and Ultra-Low Overnight rate
            plans, as of November 2025 — applied hour by hour to the same
            times the carbon optimizer picks. Ontario&rsquo;s cheapest hours
            and its cleanest hours mostly overlap overnight, which is why
            moving one load pays off twice.
          </p>
          <p>
            As a sanity check, we compare our numbers against Electricity Maps,
            an independent source. Our Ontario average intensity lands within
            2.1 g/kWh of theirs, and the two move together closely (correlation
            0.91), measured the same way.
          </p>
        </div>

        <div className="space-y-4">
          {card && (
            <div className="rounded-xl border border-line bg-surface p-5">
              <h3 className="mb-1 text-sm font-medium text-ink">
                Lifecycle emission factors (IPCC AR5), g CO₂eq/kWh
              </h3>
              <p className="mb-3 text-[11px] leading-relaxed text-ink-3">
                How much carbon pollution each energy source creates over its
                entire lifetime to generate one kilowatt-hour of electricity.
              </p>
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
              Our model covers about{" "}
              {Math.round(card.mef_method.mean_sum_slope * 100)}% of
              Ontario&rsquo;s extra power demand. The rest is imported from
              neighbouring power grids outside the province where emissions
              aren&rsquo;t tracked. All other details are in{" "}
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
