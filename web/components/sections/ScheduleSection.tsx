"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import DayBand from "@/components/DayBand";
import WakeBedPicker from "@/components/WakeBedPicker";
import {
  Forecast,
  postSchedule,
  ScheduleResult,
  ScheduleWindow,
  torontoTime,
} from "@/lib/api";
import { fmtKm, kmDriven } from "@/lib/impact";

const APPLIANCES = [
  { key: "dryer", label: "Dryer", duration: 1 },
  { key: "dishwasher", label: "Dishwasher", duration: 2 },
  { key: "washer", label: "Washer", duration: 1 },
  { key: "ev_charge", label: "EV charge", duration: 4 },
];

function gramsLine(w: ScheduleWindow, kwhRange: [number, number]) {
  const [lo, hi] = w.g_saved_range;
  const exact = kwhRange[0] === kwhRange[1];
  return exact ? `about ${lo} g CO₂ saved per run` : `${lo} to ${hi} g CO₂ saved per run`;
}

const dollars = (cents: number) => `$${(cents / 100).toFixed(2)}`;

function MoneyLines({ w }: { w: ScheduleWindow }) {
  const midKg = (w.g_saved_range[0] + w.g_saved_range[1]) / 2000;
  const uloWins = w.cost_best_ulo_cents < w.cost_best_cents * 0.75;
  return (
    <>
      <p className="mono mt-1.5 text-sm text-ink-2">
        {dollars(w.cost_best_cents)} at this hour vs {dollars(w.cost_worst_cents)} at the
        worst · saves {dollars(w.cents_saved)} a run
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-ink-3">
        The CO₂ saved is like skipping {fmtKm(midKg)} of driving.
        {uloWins &&
          ` On the Ultra-Low Overnight rate plan this run would cost ${dollars(w.cost_best_ulo_cents)}.`}
      </p>
    </>
  );
}

export default function ScheduleSection({
  fc,
  wake,
  bed,
  setWakeBed,
}: {
  fc: Forecast | null;
  wake: number;
  bed: number;
  setWakeBed: (w: number, b: number) => void;
}) {
  const [appliance, setAppliance] = useState("dryer");
  const [watts, setWatts] = useState("");
  const [result, setResult] = useState<ScheduleResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Requests can overlap once the hour picker is a slider. Keep a sequence
  // number so a slow earlier response cannot overwrite a newer answer.
  const seq = useRef(0);

  const run = useCallback(
    async (key: string, w: string, wk: number, bd: number) => {
      const mine = ++seq.current;
      setError(null);
      const a = APPLIANCES.find((x) => x.key === key)!;
      try {
        const r = await postSchedule({
          appliance: key,
          duration_h: a.duration,
          awake_start: wk,
          awake_end: bd,
          ...(w ? { watts: Number(w) } : {}),
        });
        if (mine === seq.current) setResult(r);
      } catch {
        if (mine === seq.current) {
          setError("The scheduler is waking up. Try again in a minute.");
        }
      }
    },
    []
  );

  // Debounced: dragging the hour slider crosses many values, and each one would
  // otherwise be its own POST. The picker still updates the readout and the day
  // band immediately — only the network call waits for the drag to settle.
  useEffect(() => {
    const t = setTimeout(() => run(appliance, watts, wake, bed), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wake, bed]);

  const constrained = result?.constrained;
  const overall = result?.overall;
  const sameAnswer = constrained && overall && constrained.best_start === overall.best_start;

  const markers = [];
  if (constrained) markers.push({ ts: constrained.best_start, label: "while you're up" });
  if (overall && !sameAnswer) markers.push({ ts: overall.best_start, label: "overall" });

  return (
    <div>
      <div>
        <h2 className="display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          When should it run?
        </h2>
        <p className="mt-2 max-w-[52ch] text-ink-2">
          Pick a load and tell us your hours. We find the cleanest start time in
          the next 24 hours.
        </p>
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_1.3fr]">
        {/* controls */}
        <div className="space-y-6">
          <div>
            <div className="mb-2 text-sm font-medium text-ink">The load</div>
            <div className="flex flex-wrap gap-2">
              {APPLIANCES.map((a) => (
                <button
                  key={a.key}
                  onClick={() => {
                    setAppliance(a.key);
                    run(a.key, watts, wake, bed);
                  }}
                  className={`rounded-full border px-4 py-1.5 text-sm transition-colors active:scale-[0.98] ${
                    appliance === a.key
                      ? "border-spruce bg-spruce text-white"
                      : "border-line bg-surface text-ink-2 hover:border-ink-3"
                  }`}
                >
                  {a.label}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2 text-sm text-ink-2">
              <label htmlFor="watts">Nameplate watts (optional):</label>
              <input
                id="watts"
                inputMode="numeric"
                placeholder="5000"
                value={watts}
                onChange={(e) => setWatts(e.target.value.replace(/\D/g, ""))}
                onBlur={() => run(appliance, watts, wake, bed)}
                className="mono w-24 rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-spruce"
              />
            </div>
          </div>

          <div>
            <div className="mb-2 text-sm font-medium text-ink">Your hours</div>
            <WakeBedPicker wake={wake} bed={bed} onChange={setWakeBed} />
            <p className="mt-2 max-w-[46ch] text-xs leading-relaxed text-ink-3">
              You need to be up to start a load. It can keep running after you
              turn in.
            </p>
          </div>

          {error && <p className="text-sm text-amber">{error}</p>}
        </div>

        {/* answers */}
        {constrained && overall && (
          <div className="space-y-4">
            <div className="rounded-xl border border-spruce/30 bg-surface p-6">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-3">
                While you&rsquo;re up
              </div>
              <div className="display mt-1 text-4xl font-bold text-spruce-deep">
                {torontoTime(constrained.best_start)}
              </div>
              <p className="mono mt-2 text-sm text-ink-2">
                {constrained.pct_saving}% less CO₂ than the worst hour ·{" "}
                {gramsLine(constrained, result!.kwh_range)}
              </p>
              <MoneyLines w={constrained} />
            </div>

            <div className="rounded-xl border border-line bg-surface p-6">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-3">
                Best overall
              </div>
              {sameAnswer ? (
                <p className="mt-1 text-sm text-ink-2">
                  Same answer. The cleanest hour of the day falls inside your
                  waking hours.
                </p>
              ) : (
                <>
                  <div className="display mt-1 text-2xl font-bold text-ink">
                    {torontoTime(overall.best_start)}
                    <span className="ml-2 align-middle text-sm font-normal text-ink-3">
                      while you sleep
                    </span>
                  </div>
                  <p className="mono mt-2 text-sm text-ink-2">
                    {overall.pct_saving}% less CO₂ · {gramsLine(overall, result!.kwh_range)}
                  </p>
                  <MoneyLines w={overall} />
                  <p className="mt-2 text-xs leading-relaxed text-ink-3">
                    A delay-start timer gets you this one: set it before bed.
                  </p>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {fc && (
        <div className="mt-10">
          <h3 className="mb-3 text-sm font-medium text-ink">On the day</h3>
          <DayBand hours={fc.hours} wake={wake} bed={bed} markers={markers} size="lg" />
        </div>
      )}
    </div>
  );
}
