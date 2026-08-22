"use client";
import { useCallback, useEffect, useState } from "react";
import { postSchedule, ScheduleResult, torontoTime } from "@/lib/api";

const APPLIANCES = [
  { key: "dryer", label: "Dryer", duration: 1 },
  { key: "dishwasher", label: "Dishwasher", duration: 2 },
  { key: "washer", label: "Washer", duration: 1 },
  { key: "ev_charge", label: "EV charge", duration: 4 },
];

export default function ApplianceScheduler({
  onResult,
}: {
  onResult?: (r: ScheduleResult) => void;
}) {
  const [appliance, setAppliance] = useState("dryer");
  const [watts, setWatts] = useState("");
  const [result, setResult] = useState<ScheduleResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (key: string, w: string) => {
    setError(null);
    const a = APPLIANCES.find((x) => x.key === key)!;
    try {
      const r = await postSchedule({
        appliance: key,
        duration_h: a.duration,
        ...(w ? { watts: Number(w) } : {}),
      });
      setResult(r);
      onResult?.(r);
    } catch {
      setError("Scheduler is warming up — try again in a minute.");
    }
  }, [onResult]);

  useEffect(() => { run("dryer", ""); }, [run]);

  return (
    <section className="rounded-xl border border-hairline bg-surface p-6">
      <h2 className="display text-xl font-semibold uppercase tracking-wide text-ink">
        When should it run?
      </h2>
      <p className="mt-1 text-sm text-ink-2">
        Pick a load. We find the cleanest window in the next 24 hours.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        {APPLIANCES.map((a) => (
          <button
            key={a.key}
            onClick={() => { setAppliance(a.key); run(a.key, watts); }}
            className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${
              appliance === a.key
                ? "border-teal bg-teal/15 text-teal-text"
                : "border-hairline text-ink-2 hover:border-ink-3"
            }`}
          >
            {a.label}
          </button>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <label htmlFor="watts" className="text-xs text-ink-3">
          Nameplate watts (optional — from the sticker):
        </label>
        <input
          id="watts" inputMode="numeric" placeholder="e.g. 5000" value={watts}
          onChange={(e) => setWatts(e.target.value.replace(/\D/g, ""))}
          onBlur={() => run(appliance, watts)}
          className="mono w-24 rounded-md border border-hairline bg-ground px-2 py-1 text-sm text-ink outline-none focus:border-teal"
        />
      </div>

      {error && <p className="mt-4 text-sm text-amber">{error}</p>}

      {result && (
        <div className="mt-5 rounded-lg border border-teal/30 bg-ground p-4">
          <div className="text-xs uppercase tracking-widest text-ink-3">Run it</div>
          <div className="display mt-1 text-3xl font-bold text-teal-text">
            {torontoTime(result.best_start)}
          </div>
          <div className="mono mt-2 text-sm text-ink-2">
            {result.pct_saving}% less CO₂ than the worst hour
            ({torontoTime(result.worst_start)})
          </div>
          <div className="mono mt-1 text-xs text-ink-3">
            ≈ {result.g_saved_range[0] === result.g_saved_range[1]
              ? `${result.g_saved_range[0]} g`
              : `${result.g_saved_range[0]}–${result.g_saved_range[1]} g`} CO₂ saved per run
            {result.kwh_range[0] !== result.kwh_range[1] &&
              " (typical-appliance range — enter watts for your exact number)"}
          </div>
        </div>
      )}
    </section>
  );
}
