"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import AiReportCard, { type ReportState } from "@/components/data/AiReportCard";
import GeminiKeyPanel from "@/components/data/GeminiKeyPanel";
import StatTiles from "@/components/data/StatTiles";
import UsageCharts from "@/components/data/UsageCharts";
import {
  AiReport,
  askInsights,
  fetchAiReport,
  fetchSample,
  GreenButtonResult,
  RateLimited,
  uploadGreenButton,
} from "@/lib/api";
import { useGeminiKey } from "@/lib/geminiKey";

/** Green Button upload and analysis. Owns the state; the tiles, charts, report
 *  and key panel below it are presentation. */
export default function DataSection() {
  const [result, setResult] = useState<GreenButtonResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [report, setReport] = useState<AiReport | null>(null);
  const [reportState, setReportState] = useState<ReportState>("idle");
  const [apiKey, setApiKey] = useGeminiKey();
  const [keyOpen, setKeyOpen] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function withBusy(fn: () => Promise<GreenButtonResult>) {
    setBusy(true);
    setError(null);
    setAnswer(null);
    setReport(null);
    setReportState("idle");
    try {
      setResult(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  /** The report is generated on its own request so the numbers above never
   *  wait on a ~20s model call. */
  const loadReport = useCallback(
    async (stats: GreenButtonResult, key: string) => {
      if (!stats.ai_available && !key) {
        setReportState("failed");
        return;
      }
      setReportState("loading");
      try {
        const r = await fetchAiReport(stats, key || undefined);
        setReport(r);
        setRemaining(r.remaining);
        setReportState("idle");
      } catch (e) {
        setReport(null);
        setReportState("failed");
        if (e instanceof RateLimited) {
          setRemaining(0);
          setKeyOpen(true);
        }
      }
    },
    []
  );

  useEffect(() => {
    if (result) loadReport(result, apiKey);
  }, [result, apiKey, loadReport]);

  async function ask() {
    if (!result || !question.trim() || asking) return;
    setAsking(true);
    setAnswer(null);
    try {
      const r = await askInsights(question.trim(), result, apiKey || undefined);
      setAnswer(r.answer);
      setRemaining(r.remaining);
    } catch (e) {
      if (e instanceof RateLimited) {
        setAnswer(e.detail);
        setRemaining(0);
        setKeyOpen(true);
      } else {
        setAnswer("Insights are unavailable right now. The numbers above still stand.");
      }
    } finally {
      setAsking(false);
    }
  }

  return (
    <div>
      <div>
        <h2 className="display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          What your meter knows
        </h2>
        <p className="mt-2 max-w-[58ch] leading-relaxed text-ink-2">
          Every Ontario utility must give you your smart-meter history as a
          Green Button file (O. Reg. 633/21). Upload yours for a full analysis
          of your habits, emissions, and bills. Files are analyzed in memory
          and never stored.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => withBusy(fetchSample)}
            disabled={busy}
            className="rounded-full bg-spruce px-6 py-3 text-sm font-medium text-white transition-transform hover:bg-spruce-deep active:scale-[0.98] disabled:opacity-50"
          >
            {busy ? "Analyzing…" : "Try sample data"}
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="rounded-full border border-line bg-surface px-6 py-3 text-sm text-ink transition-colors hover:border-ink-3 active:scale-[0.98] disabled:opacity-50"
          >
            Upload Green Button XML
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".xml"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) withBusy(() => uploadGreenButton(f));
            }}
          />
        </div>
        {error && <p className="mt-4 text-sm text-amber">{error}</p>}
      </div>

      {result && (
        <div className="mt-10 space-y-6">
          <StatTiles result={result} />
          <UsageCharts result={result} />

          <AiReportCard
            report={report}
            state={reportState}
            hasOwnKey={Boolean(apiKey)}
            remaining={remaining}
            question={question}
            onQuestionChange={setQuestion}
            onAsk={ask}
            asking={asking}
            answer={answer}
          >
            <GeminiKeyPanel
              hasKey={Boolean(apiKey)}
              open={keyOpen}
              onToggle={() => setKeyOpen(!keyOpen)}
              onSave={setApiKey}
              onClear={() => setApiKey("")}
            />
          </AiReportCard>

          <p className="max-w-[78ch] text-xs leading-relaxed text-ink-3">
            {result.sample ? "This is a synthetic sample household. " : ""}
            Assumes {result.assumption}. Dollar figures use OEB regulated rates
            effective {result.rates_effective}. Period {result.period[0]} to{" "}
            {result.period[1]}, {result.total_kwh.toLocaleString()} kWh total.
          </p>
        </div>
      )}
    </div>
  );
}
