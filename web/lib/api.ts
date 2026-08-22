const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
}

export interface ScheduleResult {
  overall: ScheduleWindow;
  constrained: ScheduleWindow | null;
  awake: [number, number] | null;
  kwh_range: [number, number];
  duration_h: number;
  stale: boolean;
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

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export const fetchForecast = () => get<Forecast>("/api/forecast");
export const fetchModelCard = () => get<ModelCard>("/api/model-card");
export const fetchSample = () => get<GreenButtonResult>("/api/greenbutton/sample");

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
