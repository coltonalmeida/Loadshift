"use client";
import { torontoTime } from "@/lib/api";

export default function StaleBadge({ stale, generatedAt }: { stale: boolean; generatedAt: string }) {
  return (
    <span
      className={`mono inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
        stale ? "border-amber/40 text-amber" : "border-teal/40 text-teal-text"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${stale ? "bg-amber" : "bg-teal-text animate-pulse"}`} />
      {stale ? "CACHED" : "LIVE"} · Ontario grid · {torontoTime(generatedAt)}
    </span>
  );
}
