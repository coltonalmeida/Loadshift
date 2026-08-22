"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import DayBand from "@/components/DayBand";
import LiveBadge from "@/components/LiveBadge";
import { fetchForecast, Forecast, torontoHour } from "@/lib/api";
import { useWakeBed } from "@/lib/prefs";

const FUEL_ORDER = ["NUCLEAR", "HYDRO", "GAS", "WIND", "SOLAR", "BIOFUEL"];

export default function Home() {
  const [fc, setFc] = useState<Forecast | null>(null);
  const [failed, setFailed] = useState(false);
  const [wake, bed] = useWakeBed();

  useEffect(() => {
    const load = () =>
      fetchForecast()
        .then((f) => {
          setFc(f);
          setFailed(false);
        })
        .catch(() => setFailed(true));
    load();
    const t = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  const now = fc?.now;
  const cleanest = fc
    ? fc.hours.reduce((a, b) => (b.marginal < a.marginal ? b : a))
    : null;

  return (
    <main className="mx-auto max-w-5xl px-5 pb-20">
      {/* hero: message left, live numbers right */}
      <section className="grid gap-10 pb-4 pt-14 lg:grid-cols-[1.2fr_1fr] lg:gap-16">
        <div>
          <h1 className="display text-4xl font-bold leading-[1.02] tracking-tight text-ink sm:text-5xl lg:text-6xl">
            Run it when the grid runs clean.
          </h1>
          <p className="mt-5 max-w-[52ch] text-lg leading-relaxed text-ink-2">
            Ontario&rsquo;s grid is mostly clean. The plant that ramps up for your
            extra load is not. We forecast the difference, hour by hour.
          </p>
          <div className="mt-7 flex items-center gap-4">
            <Link
              href="/schedule"
              className="rounded-full bg-spruce px-6 py-3 text-sm font-medium text-white transition-transform hover:bg-spruce-deep active:scale-[0.98]"
            >
              Find my hour
            </Link>
            {fc && <LiveBadge stale={fc.stale} generatedAt={fc.generated_at} />}
          </div>
        </div>

        {now && (
          <div className="flex flex-col justify-center gap-5 border-line lg:border-l lg:pl-10">
            <div>
              <div className="text-xs font-medium uppercase tracking-wide text-ink-3">
                What your load causes
              </div>
              <div className="mono mt-0.5 text-4xl text-ink">
                {Math.round(now.marginal_gco2_kwh)}
                <span className="ml-2 text-sm text-ink-3">g CO₂/kWh</span>
              </div>
            </div>
            <div>
              <div className="text-xs font-medium uppercase tracking-wide text-ink-3">
                What the news reports
              </div>
              <div className="mono mt-0.5 text-4xl text-ink-3">
                {Math.round(now.average_gco2_kwh)}
                <span className="ml-2 text-sm text-ink-3">g CO₂/kWh</span>
              </div>
            </div>
            {now.marginal_gco2_kwh > now.average_gco2_kwh * 1.05 && (
              <p className="text-sm leading-snug text-ink-2">
                Right now, an added load is{" "}
                <span className="mono text-amber">
                  {(now.marginal_gco2_kwh / now.average_gco2_kwh).toFixed(1)}×
                </span>{" "}
                dirtier than the average suggests.
              </p>
            )}
          </div>
        )}
      </section>

      {failed && !fc && (
        <p className="mt-6 rounded-lg border border-amber/30 bg-surface p-4 text-sm text-ink-2">
          The forecast service is waking up. This page retries automatically.
        </p>
      )}

      {/* the day band */}
      {fc && (
        <section className="mt-10">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="display text-2xl font-bold tracking-tight text-ink">
              Your next 24 hours
            </h2>
            {cleanest && (
              <span className="text-sm text-ink-2">
                Cleanest hour:{" "}
                <span className="mono text-spruce-deep">
                  {torontoHour(cleanest.ts)} · {cleanest.marginal} g
                </span>
              </span>
            )}
          </div>
          <DayBand
            hours={fc.hours}
            wake={wake}
            bed={bed}
            markers={cleanest ? [{ ts: cleanest.ts, label: "cleanest" }] : []}
          />
        </section>
      )}

      {/* fuel mix */}
      {now && (
        <section className="mono mt-8 flex flex-wrap gap-x-6 gap-y-1 text-xs text-ink-3">
          <span className="text-ink-2">On the grid now:</span>
          {FUEL_ORDER.filter((f) => now.fuel_mix_mw[f] > 0).map((f) => (
            <span key={f}>
              {f.toLowerCase()}{" "}
              <span className="text-ink-2">
                {now.fuel_mix_mw[f].toLocaleString()} MW
              </span>
            </span>
          ))}
        </section>
      )}

      <footer className="mt-16 border-t border-line pt-6 text-xs leading-relaxed text-ink-3">
        Live data from IESO Public Reports and Open-Meteo. Emission factors from
        IPCC AR5. Built at Ignition Hacks V.7.{" "}
        <a
          className="underline decoration-line underline-offset-2 hover:text-ink-2"
          href="https://github.com/coltonalmeida/Loadshift"
        >
          Source and assumptions
        </a>
        .
      </footer>
    </main>
  );
}
