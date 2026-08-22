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
import {
  askInsights,
  fetchSample,
  GreenButtonResult,
  hourLabel,
  uploadGreenButton,
} from "@/lib/api";
import { fmtKm, treeSeedlings } from "@/lib/impact";

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

function HourTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: { h: number; kwh: number } }[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="mono rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="text-ink-2">{hourLabel(d.h)}</div>
      <div className="text-spruce-deep">{d.kwh} kWh avg</div>
    </div>
  );
}

function Tile({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-line bg-surface p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-3">{label}</div>
      <div className={`mono mt-1 text-2xl ${accent ? "text-spruce-deep" : "text-ink"}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[11px] leading-snug text-ink-3">{sub}</div>}
    </div>
  );
}

export default function DataSection() {
  const [result, setResult] = useState<GreenButtonResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function withBusy(fn: () => Promise<GreenButtonResult>) {
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      setResult(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function ask() {
    if (!result || !question.trim() || asking) return;
    setAsking(true);
    setAnswer(null);
    try {
      setAnswer(await askInsights(question.trim(), result));
    } catch {
      setAnswer("Insights are unavailable right now. The numbers above still stand.");
    } finally {
      setAsking(false);
    }
  }

  const timingPct = result ? Math.round(Math.abs(result.timing_score - 1) * 100) : 0;
  const uloCheaper = result ? result.cost_ulo < result.cost_tou : false;

  return (
    <div>
      <div>
        <h2 className="display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          What your meter knows
        </h2>
        <p className="mt-2 max-w-[58ch] leading-relaxed text-ink-2">
          Every Ontario utility must give you your smart-meter history as a
          Green Button file (O. Reg. 633/21). Upload yours for a full analysis
          of your habits, emissions, and bills. Files are analyzed in memory
          and never stored.
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
          {/* headline numbers: carbon + money */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Tile label="Emissions last year" value={`${result.actual_kg} kg CO₂`} />
            <Tile
              label="Recoverable by shifting"
              value={`${result.saved_kg} kg (${result.pct_saving}%)`}
              sub={`like ${fmtKm(result.saved_kg)} of driving, or ${treeSeedlings(result.saved_kg).toFixed(1)} tree seedlings grown a decade`}
              accent
            />
            <Tile
              label="Bill savings in the same shift"
              value={`$${result.saved_tou.toFixed(0)}/yr`}
              sub={`on top of a $${result.cost_tou.toFixed(0)} year at Time-of-Use rates`}
              accent
            />
          </div>

          {/* habits */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Tile
              label="Timing score"
              value={result.timing_score.toFixed(2)}
              sub={
                result.timing_score > 1.005
                  ? `your usage lands in hours ${timingPct}% dirtier than the grid's average hour`
                  : result.timing_score < 0.995
                  ? `your usage already favors cleaner hours (${timingPct}% better than average)`
                  : "your timing is about neutral; the recoverable savings above are your upside"
              }
            />
            <Tile
              label="Evening peak share"
              value={`${Math.round(result.evening_peak_share * 100)}%`}
              sub="of your usage falls 5 to 9 PM, the dirtiest and priciest window"
            />
            <Tile
              label="Rate plan check"
              value={uloCheaper ? "ULO wins" : "TOU wins"}
              sub={`Time-of-Use $${result.cost_tou.toFixed(0)} vs Ultra-Low Overnight $${result.cost_ulo.toFixed(0)} for your actual pattern`}
            />
          </div>

          {/* charts */}
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-line bg-surface p-5">
              <h3 className="mb-4 text-sm font-medium text-ink">
                Your average day, hour by hour
              </h3>
              <div className="h-[180px]">
                <ResponsiveContainer>
                  <BarChart
                    data={result.usage_by_hour.map((kwh, h) => ({ h, kwh }))}
                    margin={{ top: 4, right: 0, left: -22, bottom: 0 }}
                    barCategoryGap={2}
                  >
                    <XAxis
                      dataKey="h"
                      tickLine={false}
                      axisLine={{ stroke: "var(--line)" }}
                      ticks={[0, 6, 12, 18, 23]}
                      tickFormatter={(h: number) => hourLabel(h)}
                      tick={{ fill: "var(--ink-3)", fontSize: 10, fontFamily: "var(--font-spline-mono)" }}
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "var(--ink-3)", fontSize: 10, fontFamily: "var(--font-spline-mono)" }}
                    />
                    <Tooltip content={<HourTooltip />} cursor={{ fill: "var(--surface-2)" }} />
                    <Bar dataKey="kwh" fill="var(--spruce)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-[11px] text-ink-3">
                kWh per hour, averaged across the year. The 5 to 9 PM window is
                where shifting pays most.
              </p>
            </div>

            <div className="rounded-xl border border-line bg-surface p-5">
              <h3 className="mb-4 text-sm font-medium text-ink">
                Monthly emissions, weighted by marginal intensity
              </h3>
              <div className="h-[180px]">
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
              <p className="mt-2 text-[11px] text-ink-3">
                Heaviest single days: {result.worst_days.map((d) => `${d.date} (${d.kg} kg)`).join(", ")}.
              </p>
            </div>
          </div>

          {/* AI report */}
          {result.ai_report && (
            <div className="rounded-xl border border-spruce/30 bg-surface p-6">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="text-sm font-medium text-ink">Your energy report</h3>
                <span className="mono rounded-full border border-line px-2.5 py-0.5 text-[10px] text-ink-3">
                  AI-generated · Gemini
                </span>
              </div>
              <p className="max-w-[72ch] text-sm leading-relaxed text-ink-2">
                {result.ai_report.summary}
              </p>
              <ol className="mt-4 space-y-2">
                {result.ai_report.recommendations.map((r, i) => (
                  <li key={i} className="flex gap-3 text-sm leading-relaxed text-ink-2">
                    <span className="mono text-spruce-deep">{i + 1}.</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ol>

              {/* follow-up */}
              <div className="mt-5 border-t border-line pt-4">
                <label htmlFor="ask" className="text-xs text-ink-3">
                  Ask a follow-up about your data
                </label>
                <div className="mt-2 flex gap-2">
                  <input
                    id="ask"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && ask()}
                    placeholder="Why is my evening usage a problem?"
                    maxLength={300}
                    className="w-full max-w-md rounded-md border border-line bg-ground px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-spruce"
                  />
                  <button
                    onClick={ask}
                    disabled={asking || !question.trim()}
                    className="rounded-md bg-ink px-4 py-2 text-sm text-surface transition-transform active:scale-[0.98] disabled:opacity-40"
                  >
                    {asking ? "Thinking…" : "Ask"}
                  </button>
                </div>
                {answer && (
                  <p className="mt-3 max-w-[72ch] rounded-md bg-ground p-3 text-sm leading-relaxed text-ink-2">
                    {answer}
                  </p>
                )}
              </div>
            </div>
          )}

          <p className="max-w-[78ch] text-xs leading-relaxed text-ink-3">
            {result.sample ? "This is a synthetic sample household. " : ""}
            Assumes {result.assumption}. Dollar figures use OEB regulated rates
            effective {result.rates_effective}. Period {result.period[0]} to{" "}
            {result.period[1]}, {result.total_kwh.toLocaleString()} kWh total.
          </p>
        </div>
      )}
    </div>
  );
}
