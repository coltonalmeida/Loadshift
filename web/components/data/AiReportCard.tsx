"use client";
import type { ReactNode } from "react";
import { AiReport } from "@/lib/api";

export type ReportState = "idle" | "loading" | "failed";

/** Said before the visitor hits the wall, not after. Null means we have not
 *  learned the remaining allowance yet, so promising a number would be a guess. */
function allowanceNote(hasOwnKey: boolean, remaining: number | null): string | null {
  if (hasOwnKey) return "Running on your own key, so there is no shared limit.";
  if (remaining === null) return null;
  if (remaining > 0) {
    const questions = remaining === 1 ? "question" : "questions";
    return `Shared key: about ${remaining} ${questions} left. Add your own key below for more.`;
  }
  return "The shared key is used up. Add your own key below to keep asking.";
}

/** The generated report and the follow-up box.
 *
 *  The report arrives on its own request, so this renders three states and the
 *  ask box stands on its own in all of them: a spent quota must not take the
 *  follow-up away, and every number outside this card is computed server-side
 *  and stands whether or not the model answered. */
export default function AiReportCard({
  report,
  state,
  hasOwnKey,
  remaining,
  question,
  onQuestionChange,
  onAsk,
  asking,
  answer,
  children,
}: {
  report: AiReport | null;
  state: ReportState;
  hasOwnKey: boolean;
  remaining: number | null;
  question: string;
  onQuestionChange: (q: string) => void;
  onAsk: () => void;
  asking: boolean;
  answer: string | null;
  /** The key panel, rendered inside this card at the bottom. */
  children?: ReactNode;
}) {
  const allowance = allowanceNote(hasOwnKey, remaining);

  return (
    <div className="rounded-xl border border-spruce/30 bg-surface p-6">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-ink">Your energy report</h3>
        <span className="mono rounded-full border border-line px-2.5 py-0.5 text-[10px] text-ink-3">
          AI-generated · Gemini
        </span>
      </div>

      {state === "loading" && (
        <div className="space-y-2" aria-live="polite">
          <p className="text-sm text-ink-3">Writing your report…</p>
          <div className="h-3 w-full max-w-[60ch] animate-pulse rounded bg-surface-2" />
          <div className="h-3 w-full max-w-[52ch] animate-pulse rounded bg-surface-2" />
          <div className="h-3 w-full max-w-[38ch] animate-pulse rounded bg-surface-2" />
        </div>
      )}

      {state === "failed" && (
        <p className="max-w-[72ch] text-sm leading-relaxed text-ink-2">
          The report is unavailable right now; the shared quota may be spent.
          Every number above is computed on our own server and stands without it.
          Add your own Gemini key below to generate one.
        </p>
      )}

      {state === "idle" && report && (
        <>
          <p className="max-w-[72ch] text-sm leading-relaxed text-ink-2">
            {report.summary}
          </p>
          <ol className="mt-4 space-y-2">
            {report.recommendations.map((r, i) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed text-ink-2">
                <span className="mono text-spruce-deep">{i + 1}.</span>
                <span>{r}</span>
              </li>
            ))}
          </ol>
        </>
      )}

      <div className="mt-5 border-t border-line pt-4">
        <label htmlFor="ask" className="text-xs text-ink-3">
          Ask a follow-up about your data
        </label>
        <div className="mt-2 flex gap-2">
          <input
            id="ask"
            value={question}
            onChange={(e) => onQuestionChange(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onAsk()}
            placeholder="Why is my evening usage a problem?"
            maxLength={300}
            className="w-full max-w-md rounded-md border border-line bg-ground px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-spruce"
          />
          <button
            onClick={onAsk}
            disabled={asking || !question.trim()}
            className="rounded-md bg-ink px-4 py-2 text-sm text-surface transition-transform active:scale-[0.98] disabled:opacity-40"
          >
            {asking ? "Thinking…" : "Ask"}
          </button>
        </div>
        {allowance && (
          <p className="mt-2 text-[11px] leading-relaxed text-ink-3">{allowance}</p>
        )}
        {answer && (
          <p className="mt-3 max-w-[72ch] whitespace-pre-line rounded-md bg-ground p-3 text-sm leading-relaxed text-ink-2">
            {answer}
          </p>
        )}
      </div>

      {children}
    </div>
  );
}
