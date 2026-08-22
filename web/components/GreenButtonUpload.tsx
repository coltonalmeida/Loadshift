"use client";
import { useRef, useState } from "react";
import {
  Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fetchSample, GreenButtonResult, uploadGreenButton } from "@/lib/api";

function MonthTooltip({ active, payload }: {
  active?: boolean;
  payload?: { payload: { month: string; kg: number; kwh: number } }[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="mono rounded-md border border-hairline bg-surface-2 px-3 py-2 text-xs">
      <div className="text-ink-2">{d.month}</div>
      <div className="text-teal-text">{d.kg} kg CO₂</div>
      <div className="text-ink-3">{d.kwh} kWh</div>
    </div>
  );
}

export default function GreenButtonUpload() {
  const [result, setResult] = useState<GreenButtonResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function withBusy(fn: () => Promise<GreenButtonResult>) {
    setBusy(true); setError(null);
    try { setResult(await fn()); }
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(false); }
  }

  return (
    <section className="rounded-xl border border-hairline bg-surface p-6">
      <h2 className="display text-xl font-semibold uppercase tracking-wide text-ink">
        Your meter, your number
      </h2>
      <p className="mt-1 text-sm text-ink-2">
        Every Ontario utility must give you your smart-meter data (Green Button,
        O.&nbsp;Reg.&nbsp;633/21). Upload the XML and see what shifting would have saved you.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="rounded-md border border-hairline px-4 py-2 text-sm text-ink hover:border-ink-3 disabled:opacity-50"
        >
          Upload Green Button XML
        </button>
        <input
          ref={fileRef} type="file" accept=".xml" className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) withBusy(() => uploadGreenButton(f));
          }}
        />
        <button
          onClick={() => withBusy(fetchSample)}
          disabled={busy}
          className="rounded-md border border-teal/40 bg-teal/10 px-4 py-2 text-sm text-teal-text hover:bg-teal/20 disabled:opacity-50"
        >
          {busy ? "Analyzing…" : "Try sample data"}
        </button>
      </div>

      {error && <p className="mt-4 text-sm text-amber">{error}</p>}

      {result && (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "actual", value: `${result.actual_kg} kg` },
              { label: "if shifted", value: `${result.optimal_kg} kg` },
              { label: "saved", value: `${result.pct_saving}%`, accent: true },
            ].map((s) => (
              <div key={s.label} className="rounded-lg bg-ground p-3">
                <div className="text-xs uppercase tracking-widest text-ink-3">{s.label}</div>
                <div className={`mono mt-1 text-lg ${s.accent ? "text-teal-text" : "text-ink"}`}>
                  {s.value}
                </div>
              </div>
            ))}
          </div>
          <div className="h-[160px]">
            <ResponsiveContainer>
              <BarChart data={result.monthly} margin={{ top: 4, right: 0, left: -20, bottom: 0 }} barCategoryGap={2}>
                <XAxis
                  dataKey="month" tickLine={false} axisLine={{ stroke: "var(--hairline)" }}
                  tick={{ fill: "var(--ink-3)", fontSize: 10, fontFamily: "var(--font-plex-mono)" }}
                  tickFormatter={(m: string) => m.slice(5)}
                />
                <YAxis
                  tickLine={false} axisLine={false}
                  tick={{ fill: "var(--ink-3)", fontSize: 10, fontFamily: "var(--font-plex-mono)" }}
                />
                <Tooltip content={<MonthTooltip />} cursor={{ fill: "var(--surface-2)" }} />
                <Bar dataKey="kg" fill="var(--teal)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-ink-3">
            {result.sample && "Synthetic sample household. "}
            Assumes {result.assumption}. Period {result.period[0]} → {result.period[1]},
            {" "}{result.total_kwh.toLocaleString()} kWh, emissions weighted by our historical
            marginal-intensity labels.
          </p>
        </div>
      )}
    </section>
  );
}
