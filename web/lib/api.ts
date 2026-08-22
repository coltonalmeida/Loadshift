// Empty in production: the browser calls same-origin /api/*, which the route
// handler at app/api/[...path] proxies to loadshift-api over Render's private
// network. Dev keeps the localhost default so `npm run dev` needs no env; the
// override exists for running the frontend against a remote API by hand.
const BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

export interface NowData {
  ts: string;
  marginal_gco2_kwh: number;
  average_gco2_kwh: number;
  fuel_mix_mw: Record<string, number>;
  ontario_demand_mw: number;
  demand_estimated: boolean;
}

export interface ForecastHour {
  ts: string;
  marginal: number;
  average: number | null;
  ci_low: number;
  ci_high: number;
}

export interface Forecast {
  generated_at: string;
  stale: boolean;
  now: NowData;
  hours: ForecastHour[];
}

export interface ScheduleWindow {
  best_start: string;
  best_gco2_kwh: number;
  worst_start: string;
  worst_gco2_kwh: number;
  pct_saving: number;
  g_saved_range: [number, number];
  cost_best_cents: number;
  cost_worst_cents: number;
  cents_saved: number;
  cost_best_ulo_cents: number;
}

export interface ScheduleResult {
  overall: ScheduleWindow;
  constrained: ScheduleWindow | null;
  awake: [number, number] | null;
  kwh_range: [number, number];
  duration_h: number;
  stale: boolean;
}

export interface AiReport {
  summary: string;
  recommendations: string[];
  model: string;
  /** Questions left on the shared key, or null when the caller brought a key. */
  remaining: number | null;
}

export interface AskResult {
  answer: string;
  remaining: number | null;
}

/** The shared key is spent or the caller used up their allowance. Distinct from
 *  a generic failure because the UI answers it differently: offer a key. */
export class RateLimited extends Error {
  constructor(public detail: string) {
    super(detail);
    this.name = "RateLimited";
  }
}

export interface GreenButtonResult {
  period: [string, string];
  total_kwh: number;
  actual_kg: number;
  optimal_kg: number;
  saved_kg: number;
  pct_saving: number;
  assumption: string;
  monthly: { month: string; kwh: number; kg: number }[];
  usage_by_hour: number[];
  evening_peak_share: number;
  overnight_share: number;
  timing_score: number;
  worst_days: { date: string; kg: number }[];
  cost_tou: number;
  cost_ulo: number;
  saved_tou: number;
  rates_effective: string;
  ai_available: boolean;
  sample?: boolean;
}

export interface ModelCard {
  target: string;
  model: string;
  features: string[];
  train_rows: number;
  test_days: number;
  test_range: [string, string];
  mae_model: number;
  mae_baseline_seasonal_naive_168h: number;
  improvement_pct: number;
  test_r2: number;
  target_mean: number;
  emission_factors_gco2_kwh: Record<string, number>;
  mef_method: {
    method: string;
    citation: string;
    mean_sum_slope: number;
    note: string;
  };
}

/** Deployment facts, straight from Render's injected env plus the cron's own
 *  record of the last rebuild. Rendered in the footer so the architecture is
 *  inspectable rather than asserted. */
export interface Platform {
  platform: "render" | "local";
  service: string | null;
  service_type: string | null;
  instance: string | null;
  commit: string | null;
  branch: string | null;
  is_preview: boolean;
  cache_backend: string;
  cache_age_s: number | null;
  refresh: {
    by_service: string | null;
    by_commit: string | null;
    ran_at: string | null;
    ok: boolean | null;
    duration_s: number | null;
    generated_at: string | null;
    weather_source: string | null;
  };
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export const fetchForecast = () => get<Forecast>("/api/forecast");
export const fetchModelCard = () => get<ModelCard>("/api/model-card");
export const fetchSample = () => get<GreenButtonResult>("/api/greenbutton/sample");
export const fetchPlatform = () => get<Platform>("/api/platform");

export async function postSchedule(body: {
  appliance?: string;
  kwh?: number;
  watts?: number;
  duration_h: number;
  awake_start?: number;
  awake_end?: number;
}): Promise<ScheduleResult> {
  const r = await fetch(`${BASE}/api/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`schedule: ${r.status}`);
  return r.json();
}

/** A user's own key rides along only on the two insight calls. */
const keyHeader = (key?: string): Record<string, string> =>
  key ? { "X-Gemini-Key": key } : {};

/** Generated separately from the stats so the numbers never wait on it. */
export async function fetchAiReport(
  stats: GreenButtonResult,
  key?: string
): Promise<AiReport> {
  const r = await fetch(`${BASE}/api/insights/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...keyHeader(key) },
    body: JSON.stringify({ stats }),
  });
  if (r.status === 429) {
    const d = await r.json().catch(() => null);
    throw new RateLimited(d?.detail ?? "Shared key limit reached.");
  }
  if (!r.ok) throw new Error("report unavailable");
  return r.json();
}

export async function askInsights(
  question: string,
  stats: GreenButtonResult,
  key?: string
): Promise<AskResult> {
  const r = await fetch(`${BASE}/api/insights/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...keyHeader(key) },
    body: JSON.stringify({ question, stats }),
  });
  if (r.status === 429) {
    const d = await r.json().catch(() => null);
    throw new RateLimited(d?.detail ?? "Shared key limit reached.");
  }
  if (!r.ok) throw new Error("insights unavailable");
  const d = await r.json();
  return { answer: d.answer as string, remaining: d.remaining ?? null };
}

export async function uploadGreenButton(file: File): Promise<GreenButtonResult> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${BASE}/api/greenbutton`, { method: "POST", body: fd });
  if (!r.ok) {
    const detail = await r.json().catch(() => null);
    throw new Error(detail?.detail ?? `upload failed (${r.status})`);
  }
  return r.json();
}

export const torontoHourNum = (iso: string) =>
  Number(
    new Intl.DateTimeFormat("en-CA", {
      hour: "numeric", hourCycle: "h23", timeZone: "America/Toronto",
    }).format(new Date(iso))
  );

export const torontoHour = (iso: string) =>
  new Intl.DateTimeFormat("en-CA", {
    hour: "numeric", timeZone: "America/Toronto", hour12: true,
  }).format(new Date(iso));

export const torontoTime = (iso: string) =>
  new Intl.DateTimeFormat("en-CA", {
    weekday: "short", hour: "numeric", minute: "2-digit",
    timeZone: "America/Toronto", hour12: true,
  }).format(new Date(iso));

export const hourLabel = (h: number) => {
  const hh = ((h % 24) + 24) % 24;
  if (hh === 0) return "12 AM";
  if (hh === 12) return "12 PM";
  return hh < 12 ? `${hh} AM` : `${hh - 12} PM`;
};
