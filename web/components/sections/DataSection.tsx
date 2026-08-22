"use client";
import { useRef, useState } from "react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchSample, GreenButtonResult, uploadGreenButton } from "@/lib/api";

function MonthTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: { month: string; kg: number; kwh: number } }[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="mono rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="text-ink-2">{d.month}</div>
      <div className="text-spruce-deep">{d.kg} kg CO₂</div>
      <div className="text-ink-3">{d.kwh} kWh</div>
    </div>
  );
}

export default function DataSection() {
  const [result, setResult] = useState<GreenButtonResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function withBusy(fn: () => Promise<GreenButtonResult>) {
    setBusy(true);
    setError(null);
    try {
      setResult(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div>
        <h2 className="display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          What your meter knows
        </h2>
        <p className="mt-2 max-w-[58ch] leading-relaxed text-ink-2">
          Every Ontario utility must give you your smart-meter history as a
          Green Button file (O. Reg. 633/21). Upload yours and see what shifting
          would have saved over the past year. Files are analyzed in memory and
          never stored.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => withBusy(fetchSample)}
            disabled={busy}
            className="rounded-full bg-spruce px-6 py-3 text-sm font-medium text-white transition-transform hover:bg-spruce-deep active:scale-[0.98] disabled:opacity-50"
          >
            {busy ? "Analyzing…" : "Try sample data"}
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="rounded-full border border-line bg-surface px-6 py-3 text-sm text-ink transition-colors hover:border-ink-3 active:scale-[0.98] disabled:opacity-50"
          >
            Upload Green Button XML
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".xml"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) withBusy(() => uploadGreenButton(f));
            }}
          />
        </div>
        {error && <p className="mt-4 text-sm text-amber">{error}</p>}
      </div>

      {result && (
        <div className="mt-10 space-y-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[
              { label: "Actual emissions", value: `${result.actual_kg} kg` },
              { label: "If shifted", value: `${result.optimal_kg} kg` },
              { label: "Recoverable", value: `${result.saved_kg} kg (${result.pct_saving}%)`, accent: true },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border border-line bg-surface p-5">
                <div className="text-xs font-medium uppercase tracking-wide text-ink-3">
                  {s.label}
                </div>
                <div
                  className={`mono mt-1 text-2xl ${s.accent ? "text-spruce-deep" : "text-ink"}`}
                >
                  {s.value}
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-line bg-surface p-5">
            <h3 className="mb-4 text-sm font-medium text-ink">
              Monthly emissions, weighted by marginal intensity
            </h3>
            <div className="h-[200px]">
              <ResponsiveContainer>
                <BarChart
                  data={result.monthly}
                  margin={{ top: 4, right: 0, left: -18, bottom: 0 }}
                  barCategoryGap={2}
                >
                  <XAxis
                    dataKey="month"
                    tickLine={false}
                    axisLine={{ stroke: "var(--line)" }}
                    tick={{ fill: "var(--ink-3)", fontSize: 10, fontFamily: "var(--font-spline-mono)" }}
                    tickFormatter={(m: string) => m.slice(5)}
                  />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: "var(--ink-3)", fontSize: 10, fontFamily: "var(--font-spline-mono)" }}
                  />
                  <Tooltip content={<MonthTooltip />} cursor={{ fill: "var(--surface-2)" }} />
                  <Bar dataKey="kg" fill="var(--spruce)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <p className="max-w-[70ch] text-xs leading-relaxed text-ink-3">
            {result.sample ? "This is a synthetic sample household. " : ""}
            Assumes {result.assumption}. Period {result.period[0]} to{" "}
            {result.period[1]}, {result.total_kwh.toLocaleString()} kWh total.
          </p>
        </div>
      )}
    </div>
  );
}
