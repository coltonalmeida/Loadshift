"use client";
import { useEffect, useState } from "react";
import { fetchPlatform, type Platform } from "@/lib/api";

/** Where this page's forecast came from.
 *
 *  Real operational telemetry, not decoration: the forecast is built by a
 *  separate Render cron job and published to Key Value, and the web service
 *  only ever reads it. That split is invisible from the outside unless the site
 *  says so, and it is the reason a redeploy no longer empties the cache.
 *
 *  Renders nothing if /api/platform is unreachable — a footer must never be the
 *  thing that breaks the page. */
export default function PlatformStrip() {
  const [p, setP] = useState<Platform | null>(null);

  useEffect(() => {
    let alive = true;
    fetchPlatform()
      .then((d) => alive && setP(d))
      .catch(() => {});
    // Re-read on the cron's cadence so a rebuild shows up without a reload.
    const t = setInterval(() => {
      fetchPlatform()
        .then((d) => alive && setP(d))
        .catch(() => {});
    }, 60_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (!p) return null;

  const onRender = p.platform === "render";
  const durable = p.cache_backend === "render-key-value";
  const built = p.refresh.by_service;

  return (
    <div className="mono mt-16 border-t border-line pt-6 text-xs text-ink-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="inline-flex items-center gap-2 text-ink-2">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              durable ? "bg-spruce" : "bg-amber"
            }`}
          />
          {onRender ? "Running on Render" : "Running locally"}
        </span>

        {built && (
          <span>
            forecast built by{" "}
            <span className="text-ink-2">{built}</span>
            {p.refresh.duration_s != null && ` in ${p.refresh.duration_s}s`}
            {p.refresh.ran_at && ` · ${ago(p.refresh.ran_at)}`}
          </span>
        )}

        <span>
          cache{" "}
          <span className={durable ? "text-ink-2" : "text-amber"}>
            {durable ? "Render Key Value" : p.cache_backend}
          </span>
        </span>

        {p.commit && (
          <span>
            commit <span className="text-ink-2">{p.commit}</span>
            {p.branch && p.branch !== "main" && ` (${p.branch})`}
          </span>
        )}

        {p.is_preview && (
          <span className="rounded-full border border-amber/40 bg-amber/5 px-2 py-0.5 text-amber">
            preview environment
          </span>
        )}

        {p.refresh.ok === false && (
          <span className="text-amber">
            last rebuild failed · serving last-known-good
          </span>
        )}
      </div>
    </div>
  );
}

function ago(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (!Number.isFinite(mins) || mins < 0) return "just now";
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h === 1 ? "1 hour ago" : `${h} hours ago`;
}
