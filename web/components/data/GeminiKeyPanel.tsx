"use client";
import { useState } from "react";

/** Bring-your-own-key disclosure.
 *
 *  The draft lives here rather than in the parent: nothing above this component
 *  needs a half-typed key, and the saved key is only ever handed upward through
 *  onSave. `hasKey` is a boolean on purpose — the panel renders the same either
 *  way and never needs the secret itself. */
export default function GeminiKeyPanel({
  hasKey,
  open,
  onToggle,
  onSave,
  onClear,
}: {
  hasKey: boolean;
  open: boolean;
  onToggle: () => void;
  onSave: (key: string) => void;
  onClear: () => void;
}) {
  const [draft, setDraft] = useState("");

  function save() {
    if (!draft.trim()) return;
    onSave(draft);
    setDraft("");
  }

  return (
    <div className="mt-4 border-t border-line pt-4">
      <button
        onClick={onToggle}
        className="text-xs text-ink-3 underline-offset-2 hover:text-ink-2 hover:underline"
      >
        {hasKey ? "Using your own Gemini API key" : "Use your own Gemini API key"}
      </button>
      {open && (
        <div className="mt-3">
          <div className="flex flex-wrap gap-2">
            <input
              type="password"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && save()}
              placeholder={hasKey ? "Saved. Paste a new key to replace it." : "Paste your key"}
              autoComplete="off"
              spellCheck={false}
              className="w-full max-w-md rounded-md border border-line bg-ground px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-spruce"
            />
            <button
              onClick={save}
              disabled={!draft.trim()}
              className="rounded-md bg-ink px-4 py-2 text-sm text-surface transition-transform active:scale-[0.98] disabled:opacity-40"
            >
              Save
            </button>
            {hasKey && (
              <button
                onClick={onClear}
                className="rounded-md border border-line px-4 py-2 text-sm text-ink-2 transition-colors hover:border-ink-3"
              >
                Clear
              </button>
            )}
          </div>
          <p className="mt-2 max-w-[72ch] text-[11px] leading-relaxed text-ink-3">
            API keys are never written to our server or its logs. A free key takes
            a minute at aistudio.google.com/apikey
          </p>
        </div>
      )}
    </div>
  );
}
