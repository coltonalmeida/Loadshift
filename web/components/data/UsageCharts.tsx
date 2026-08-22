"use client";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { GreenButtonResult, hourLabel } from "@/lib/api";

/** Recharts passes the whole datum through; both tooltips read one series. */
const TICK = { fill: "var(--ink-3)", fontSize: 10, fontFamily: "var(--font-spline-mono)" };

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

/** The shape of the year: the household's average day, and its month-by-month
 *  emissions weighted by the marginal intensity of the hours they used. */
export default function UsageCharts({ result }: { result: GreenButtonResult }) {
  return (
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
                tick={TICK}
              />
              <YAxis tickLine={false} axisLine={false} tick={TICK} />
              <Tooltip content={<HourTooltip />} cursor={{ fill: "var(--surface-2)" }} />
              <Bar dataKey="kwh" fill="var(--spruce)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[11px] text-ink-3">
          kWh per hour, averaged across the year. The 5 to 9 PM window is where
          shifting pays most.
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
                tick={TICK}
                tickFormatter={(m: string) => m.slice(5)}
              />
              <YAxis tickLine={false} axisLine={false} tick={TICK} />
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
  );
}
