"use client";
import { ForecastHour, hourLabel, torontoHourNum, torontoTime } from "@/lib/api";
import { intensityColor } from "@/lib/colors";
import { isAwake } from "@/lib/prefs";

interface Marker {
  ts: string;
  label: string;
}

interface Props {
  hours: ForecastHour[];
  wake?: number;
  bed?: number;
  markers?: Marker[]; // e.g. best start hours to flag on the band
  size?: "lg" | "sm";
}

/** The Day Band: the next 24 hours as a single strip, each hour painted by
 *  forecast marginal intensity (spruce = clean, amber = dirty). Hours where
 *  the viewer is asleep are dimmed into night. */
export default function DayBand({ hours, wake, bed, markers = [], size = "lg" }: Props) {
  if (!hours.length) return null;
  const values = hours.map((h) => h.marginal);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const markerTs = new Map(markers.map((m) => [m.ts, m.label]));
  const cellH = size === "lg" ? "h-20 sm:h-24" : "h-10";
  const hasSleep = wake !== undefined && bed !== undefined;

  return (
    <div>
      {/* flags above the band */}
      {markers.length > 0 && (
        <div className="relative mb-1 h-5">
          {hours.map((h, i) =>
            markerTs.has(h.ts) ? (
              <span
                key={h.ts}
                className="mono absolute -translate-x-1/2 whitespace-nowrap text-xs font-medium text-spruce-deep"
                style={{ left: `${((i + 0.5) / hours.length) * 100}%` }}
              >
                {markerTs.get(h.ts)} ▾
              </span>
            ) : null
          )}
        </div>
      )}

      <div className="day-band-cells flex gap-px overflow-hidden rounded-lg">
        {hours.map((h) => {
          const localH = torontoHourNum(h.ts);
          const asleep = hasSleep && !isAwake(localH, wake!, bed!);
          const flagged = markerTs.has(h.ts);
          return (
            <div key={h.ts} className={`group relative flex-1 ${cellH}`}>
              <div
                className={`h-full w-full transition-opacity ${
                  asleep ? "opacity-100" : ""
                } ${flagged ? "ring-2 ring-inset ring-ink" : ""}`}
                style={{
                  background: asleep
                    ? `color-mix(in oklab, ${intensityColor(h.marginal, min, max)} 30%, var(--night))`
                    : intensityColor(h.marginal, min, max),
                }}
                aria-label={`${torontoTime(h.ts)}: ${h.marginal} grams CO2 per kilowatt hour${asleep ? ", while you sleep" : ""}`}
                role="img"
              />
              {/* hover tooltip */}
              <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-surface px-2.5 py-1.5 shadow-sm group-hover:block">
                <div className="mono text-xs text-ink">{h.marginal} g/kWh</div>
                <div className="mono text-[10px] text-ink-3">
                  {torontoTime(h.ts)}
                  {asleep ? " · asleep" : ""}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* time ticks */}
      <div className="mono mt-1.5 flex justify-between text-[11px] text-ink-3">
        <span>now</span>
        {[6, 12, 18].map((offset) => {
          const h = hours[Math.min(offset, hours.length - 1)];
          return <span key={offset}>{hourLabel(torontoHourNum(h.ts))}</span>;
        })}
        <span>+24h</span>
      </div>

      {size === "lg" && (
        <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-3">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--spruce)" }} />
            cleaner
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--amber)" }} />
            dirtier
          </span>
          {hasSleep && (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--night)" }} />
              while you sleep
            </span>
          )}
        </div>
      )}
    </div>
  );
}
