"use client";
import {
  Area, ComposedChart, Line, ReferenceArea, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { ForecastHour, torontoHour, torontoTime } from "@/lib/api";

interface Props {
  hours: ForecastHour[];
  bestStart?: string;
  durationH?: number;
}

interface Row extends ForecastHour {
  ci: [number, number];
  label: string;
}

function ChartTooltip({ active, payload }: {
  active?: boolean;
  payload?: { payload: Row }[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="mono rounded-md border border-hairline bg-surface-2 px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 text-ink-2">{torontoTime(d.ts)}</div>
      <div className="text-teal-text">marginal {d.marginal} g/kWh</div>
      {d.average != null && <div className="text-peri">average&nbsp;&nbsp;{d.average} g/kWh</div>}
      <div className="text-ink-3">80% CI {d.ci_low}–{d.ci_high}</div>
    </div>
  );
}

export default function IntensityCurve({ hours, bestStart, durationH = 1 }: Props) {
  const data: Row[] = hours.map((h) => ({
    ...h,
    ci: [h.ci_low, h.ci_high],
    label: torontoHour(h.ts),
  }));

  let bandX1: string | undefined, bandX2: string | undefined;
  if (bestStart) {
    const i = data.findIndex((d) => d.ts === bestStart);
    if (i >= 0) {
      // pad a half-slot each side so a 1-hour window still has visible width
      bandX1 = data[Math.max(i - 1, 0)].label;
      bandX2 = data[Math.min(i + durationH, data.length - 1)].label;
    }
  }

  return (
    <div className="h-[340px] w-full">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 12, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id="ciFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--teal)" stopOpacity={0.18} />
              <stop offset="100%" stopColor="var(--teal)" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="label" tickLine={false} axisLine={{ stroke: "var(--hairline)" }}
            tick={{ fill: "var(--ink-3)", fontSize: 11, fontFamily: "var(--font-plex-mono)" }}
            interval={2}
          />
          <YAxis
            tickLine={false} axisLine={false} width={52}
            tick={{ fill: "var(--ink-3)", fontSize: 11, fontFamily: "var(--font-plex-mono)" }}
            domain={["dataMin - 20", "dataMax + 20"]}
            tickFormatter={(v: number) => String(Math.round(v))}
          />
          {bandX1 && (
            <ReferenceArea
              x1={bandX1} x2={bandX2} fill="var(--teal)" fillOpacity={0.14}
              stroke="var(--teal)" strokeOpacity={0.5} strokeDasharray="3 3"
            />
          )}
          <Area dataKey="ci" stroke="none" fill="url(#ciFill)" connectNulls />
          <Line
            dataKey="average" stroke="var(--peri)" strokeWidth={1.5}
            strokeDasharray="5 4" dot={false} connectNulls
          />
          <Line
            dataKey="marginal" stroke="var(--teal-text)" strokeWidth={2}
            dot={false} activeDot={{ r: 4, fill: "var(--teal-text)", stroke: "var(--ground)", strokeWidth: 2 }}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--ink-3)", strokeDasharray: "2 4" }} />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="mono mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-2">
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-0.5 w-5 bg-teal-text" /> marginal intensity (forecast, g CO₂/kWh)
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-0 w-5 border-t border-dashed border-peri" /> grid average (same hour yesterday)
        </span>
        {bandX1 && (
          <span className="inline-flex items-center gap-2">
            <span className="inline-block h-2.5 w-5 border border-dashed border-teal bg-teal/15" /> recommended window
          </span>
        )}
      </div>
    </div>
  );
}
