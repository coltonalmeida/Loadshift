"use client";
import { torontoTime } from "@/lib/api";

/** Live/cached data indicator. The dot conveys real state: green pulsing
 *  means the hourly refresh is current; amber means serving last-known-good. */
export default function LiveBadge({
  stale,
  generatedAt,
}: {
  stale: boolean;
  generatedAt: string;
}) {
  return (
    <span
      className={`mono inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
        stale
          ? "border-amber/40 bg-amber/5 text-amber"
          : "border-spruce/30 bg-spruce/5 text-spruce-deep"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          stale ? "bg-amber" : "animate-pulse bg-spruce"
        }`}
      />
      {stale ? "Cached" : "Live"} · Ontario grid · {torontoTime(generatedAt)}
    </span>
  );
}
