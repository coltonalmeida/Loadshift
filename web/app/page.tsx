"use client";
import { useEffect, useState } from "react";
import ApplianceScheduler from "@/components/ApplianceScheduler";
import GreenButtonUpload from "@/components/GreenButtonUpload";
import IntensityCurve from "@/components/IntensityCurve";
import ModelCard from "@/components/ModelCard";
import StaleBadge from "@/components/StaleBadge";
import { fetchForecast, Forecast, ScheduleResult } from "@/lib/api";

const FUEL_ORDER = ["NUCLEAR", "HYDRO", "GAS", "WIND", "SOLAR", "BIOFUEL"];

export default function Home() {
  const [fc, setFc] = useState<Forecast | null>(null);
  const [failed, setFailed] = useState(false);
  const [sched, setSched] = useState<ScheduleResult | null>(null);

  useEffect(() => {
    const load = () => fetchForecast().then((f) => { setFc(f); setFailed(false); })
      .catch(() => setFailed(true));
    load();
    const t = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  const now = fc?.now;
  const ratio = now ? (now.marginal_gco2_kwh / now.average_gco2_kwh).toFixed(1) : null;

  return (
    <main className="mx-auto max-w-5xl px-5 pb-16">
      {/* top bar */}
      <header className="flex flex-wrap items-center justify-between gap-3 py-6">
        <span className="display text-2xl font-bold uppercase tracking-[0.25em] text-ink">
          Load<span className="text-teal-text">shift</span>
        </span>
        {fc && <StaleBadge stale={fc.stale} generatedAt={fc.generated_at} />}
      </header>

      {/* hero */}
      <section className="pt-6 pb-2">
        <h1 className="display max-w-3xl text-5xl font-bold uppercase leading-[0.95] tracking-tight text-ink sm:text-7xl">
          Your dryer doesn&rsquo;t emit
          <br />
          the grid <span className="text-ink-3 line-through decoration-ember/70 decoration-4">average</span>
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-2">
          It emits whatever turns <em className="not-italic text-ember-text">on</em> because
          of it — and in Ontario, the plant that ramps for your extra kWh is almost always
          natural gas. We forecast that <strong className="text-ink">marginal</strong> intensity
          24 hours ahead and name the cleanest hour to run.
        </p>

        {now && (
          <div className="mt-8 flex flex-wrap items-end gap-x-10 gap-y-4">
            <div>
              <div className="text-xs uppercase tracking-widest text-ink-3">
                marginal — what your load causes
              </div>
              <div className="mono mt-1 text-4xl text-teal-text sm:text-5xl">
                {Math.round(now.marginal_gco2_kwh)}
                <span className="ml-2 text-base text-ink-3">g CO₂/kWh</span>
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-widest text-ink-3">
                grid average — what the news reports
              </div>
              <div className="mono mt-1 text-4xl text-peri sm:text-5xl">
                {Math.round(now.average_gco2_kwh)}
                <span className="ml-2 text-base text-ink-3">g CO₂/kWh</span>
              </div>
            </div>
            {ratio && Number(ratio) > 1.05 && (
              <div className="pb-1 text-sm text-ink-2">
                Right now your added load is{" "}
                <span className="mono text-ember-text">{ratio}×</span> dirtier than the average
                suggests.
              </div>
            )}
          </div>
        )}

        {failed && !fc && (
          <p className="mt-8 rounded-lg border border-amber/40 bg-surface p-4 text-sm text-amber">
            The forecast service is waking up. This page retries automatically — nothing to do.
          </p>
        )}
      </section>

      {/* the 24h horizon */}
      {fc && (
        <section className="mt-8 rounded-xl border border-hairline bg-surface p-5">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="display text-xl font-semibold uppercase tracking-wide text-ink">
              The next 24 hours
            </h2>
            <span className="text-xs text-ink-3">
              times shown in Eastern — hover for detail
            </span>
          </div>
          <IntensityCurve
            hours={fc.hours}
            bestStart={sched?.best_start}
            durationH={sched?.duration_h}
          />
        </section>
      )}

      {/* fuel mix strip */}
      {now && (
        <div className="mono mt-3 flex flex-wrap gap-x-5 gap-y-1 px-1 text-xs text-ink-3">
          <span className="uppercase tracking-widest">on the grid now:</span>
          {FUEL_ORDER.filter((f) => now.fuel_mix_mw[f] > 0).map((f) => (
            <span key={f}>
              {f.toLowerCase()} <span className="text-ink-2">{now.fuel_mix_mw[f].toLocaleString()} MW</span>
            </span>
          ))}
          {now.demand_estimated && <span>(demand estimated from generation)</span>}
        </div>
      )}

      {/* scheduler + green button */}
      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <ApplianceScheduler onResult={setSched} />
        <GreenButtonUpload />
      </div>

      {/* model card */}
      <div className="mt-6">
        <ModelCard />
      </div>

      <footer className="mt-12 border-t border-hairline pt-6 text-xs leading-relaxed text-ink-3">
        Live data: IESO Public Reports (generation by fuel, Ontario demand) · Open-Meteo
        (weather features) · Green Button under O. Reg. 633/21. Emission factors: IPCC AR5
        lifecycle medians. Built at Ignition Hacks V.7 —{" "}
        <a
          className="underline decoration-hairline underline-offset-2 hover:text-ink-2"
          href="https://github.com/coltonalmeida/Loadshift"
        >
          source &amp; assumptions
        </a>
        .
      </footer>
    </main>
  );
}
