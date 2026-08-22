"use client";
import { GreenButtonResult } from "@/lib/api";
import { fmtKm, treeSeedlings } from "@/lib/impact";

export function Tile({ label, value, sub, accent }: {
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

/** Reads a load-weighted MEF ratio out loud. Above 1 the household's usage lands
 *  in hours dirtier than the period's flat average; below 1 it already favors the
 *  clean ones. The dead band keeps a score of 1.00 from being reported as a 0%
 *  effect in either direction. */
function timingNote(score: number): string {
  const pct = Math.round(Math.abs(score - 1) * 100);
  if (score > 1.005) {
    return `your usage lands in hours ${pct}% dirtier than the grid's average hour`;
  }
  if (score < 0.995) {
    return `your usage already favors cleaner hours (${pct}% better than average)`;
  }
  return "your timing is about neutral; the recoverable savings above are your upside";
}

/** The six headline numbers: what the year cost in carbon and dollars, then what
 *  the household's own timing is doing to both. */
export default function StatTiles({ result }: { result: GreenButtonResult }) {
  const uloCheaper = result.cost_ulo < result.cost_tou;

  return (
    <>
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

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Tile
          label="Timing score"
          value={result.timing_score.toFixed(2)}
          sub={timingNote(result.timing_score)}
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
    </>
  );
}
