"use client";
import { useEffect, useState } from "react";
import { fetchModelCard, ModelCard as ModelCardData } from "@/lib/api";

export default function ModelCard() {
  const [card, setCard] = useState<ModelCardData | null>(null);

  useEffect(() => {
    fetchModelCard().then(setCard).catch(() => {});
  }, []);

  if (!card) return null;

  const stats = [
    { label: "forecast MAE", value: `${card.mae_model} g`, sub: "24h-ahead, 60-day holdout" },
    { label: "seasonal-naive MAE", value: `${card.mae_baseline_seasonal_naive_168h} g`, sub: "same hour last week" },
    { label: "improvement", value: `${card.improvement_pct}%`, sub: "over the baseline", accent: true },
    { label: "test R²", value: `${card.test_r2}`, sub: "chronological split" },
  ];

  return (
    <section className="rounded-xl border border-hairline bg-surface p-6">
      <h2 className="display text-xl font-semibold uppercase tracking-wide text-ink">
        Show your work
      </h2>
      <p className="mt-1 text-sm text-ink-2">
        Marginal intensity is labelled by regressing each fuel&rsquo;s hourly ramp on demand
        ramps (Siler-Evans, Azevedo &amp; Morgan 2012), then forecast with gradient boosting.
      </p>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg bg-ground p-3">
            <div className="text-xs uppercase tracking-widest text-ink-3">{s.label}</div>
            <div className={`mono mt-1 text-xl ${s.accent ? "text-teal-text" : "text-ink"}`}>
              {s.value}
            </div>
            <div className="mt-0.5 text-[11px] text-ink-3">{s.sub}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 rounded-lg border border-ember/25 bg-ground p-4 text-xs leading-relaxed text-ink-2">
        <span className="text-ember-text">Stated limitation:</span> on average only{" "}
        <span className="mono">{Math.round(card.mef_method.mean_sum_slope * 100)}%</span> of a
        marginal Ontario kWh is explained by the fuels we model — the rest is served by
        intertie imports and exports whose emissions we do not observe. Every other
        assumption is listed in the repo&rsquo;s ASSUMPTIONS.md.
      </div>
    </section>
  );
}
