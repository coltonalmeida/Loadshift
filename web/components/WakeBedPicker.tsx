"use client";
import { hourLabel } from "@/lib/api";

/** Thumb diameter in px. Must match .wb-range in globals.css: the fill segments
 *  are positioned with the same inset the browser applies to a range thumb, so
 *  the painted awake span lines up exactly with the handles. */
const THUMB = 18;
const MAX = 23;

/** Left offset of the thumb centre at hour `v`, as a CSS length. */
const pos = (v: number) => {
  const f = v / MAX;
  const px = THUMB / 2 - f * THUMB;
  // Emit "A% - Bpx" rather than "A% + -Bpx": a negative operand after + is legal
  // calc() but needlessly close to the edge of what parsers accept.
  const sign = px < 0 ? "-" : "+";
  return `calc(${(f * 100).toFixed(4)}% ${sign} ${Math.abs(px).toFixed(2)}px)`;
};

/** Width of the span from hour `a` to hour `b`, in the same coordinate space. */
const span = (a: number, b: number) => {
  const f = (b - a) / MAX;
  return `calc(${(f * 100).toFixed(4)}% - ${(f * THUMB).toFixed(2)}px)`;
};

const TICKS = [0, 6, 12, 18, 23];

/** The awake window as positioned fill segments.
 *
 *  A day is circular and this track is a line, so a window running past midnight
 *  (bed <= wake, e.g. up at 8 AM, bed at 12 AM) is two segments, not one. This
 *  must agree with isAwake() in lib/prefs.ts, which wraps the same way — the day
 *  band below the picker is shaded by that function.
 *
 *  The wrapped segments run to the physical ends of the track rather than to the
 *  thumb centres, so the window reads as continuing around midnight instead of
 *  stopping just short of each edge.
 */
type Seg = { key: string; style: React.CSSProperties };

function segments(wake: number, bed: number): Seg[] {
  if (wake < bed) {
    return [{ key: "mid", style: { left: pos(wake), width: span(wake, bed) } }];
  }
  return [
    { key: "evening", style: { left: pos(wake), right: 0 } },
    { key: "morning", style: { left: 0, width: pos(bed) } },
  ];
}

export default function WakeBedPicker({
  wake,
  bed,
  onChange,
}: {
  wake: number;
  bed: number;
  onChange: (wake: number, bed: number) => void;
}) {
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-sm text-ink-2">I&rsquo;m up between</span>
        <span className="mono text-sm text-ink">
          {hourLabel(wake)} <span className="text-ink-3">and</span> {hourLabel(bed)}
        </span>
      </div>

      <div className="relative mt-3 h-[18px]">
        {/* asleep rail */}
        <div
          className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full"
          style={{ background: "color-mix(in oklab, var(--night) 22%, var(--surface-2))" }}
        />
        {/* awake span, one segment or two across midnight */}
        {segments(wake, bed).map((s) => (
          <div
            key={s.key}
            className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-spruce"
            style={s.style}
          />
        ))}

        {/* Two independent ranges. Deliberately NOT clamped against each other:
            bed before wake is a real answer, not an error to prevent. */}
        <input
          type="range"
          min={0}
          max={MAX}
          step={1}
          value={wake}
          onChange={(e) => onChange(Number(e.target.value), bed)}
          aria-label="Wake hour"
          aria-valuetext={hourLabel(wake)}
          className="wb-range absolute inset-0 m-0 h-full w-full"
        />
        <input
          type="range"
          min={0}
          max={MAX}
          step={1}
          value={bed}
          onChange={(e) => onChange(wake, Number(e.target.value))}
          aria-label="Bedtime hour"
          aria-valuetext={hourLabel(bed)}
          className="wb-range absolute inset-0 m-0 h-full w-full"
        />
      </div>

      <div className="relative mt-1.5 h-4">
        {TICKS.map((t) => (
          <span
            key={t}
            className="mono absolute -translate-x-1/2 text-[11px] text-ink-3"
            style={{ left: pos(t) }}
          >
            {hourLabel(t)}
          </span>
        ))}
      </div>
    </div>
  );
}
