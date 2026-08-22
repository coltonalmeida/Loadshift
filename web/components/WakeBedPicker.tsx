"use client";
import { hourLabel } from "@/lib/api";

const HOURS = Array.from({ length: 24 }, (_, i) => i);

function HourSelect({
  id,
  value,
  onChange,
}: {
  id: string;
  value: number;
  onChange: (h: number) => void;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="mono rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-spruce"
    >
      {HOURS.map((h) => (
        <option key={h} value={h}>
          {hourLabel(h)}
        </option>
      ))}
    </select>
  );
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
    <div className="flex flex-wrap items-center gap-x-2 gap-y-2 text-sm text-ink-2">
      <label htmlFor="wake">I wake at</label>
      <HourSelect id="wake" value={wake} onChange={(h) => onChange(h, bed)} />
      <label htmlFor="bed">and go to bed at</label>
      <HourSelect id="bed" value={bed} onChange={(h) => onChange(wake, h)} />
    </div>
  );
}
