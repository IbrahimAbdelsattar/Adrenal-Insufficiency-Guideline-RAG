"use client";

import { useState, useEffect, useRef } from "react";

const CLINICAL_EXAMPLES = [
  {
    label: "Symptoms & Identification",
    query: "What are the symptoms of adrenal insufficiency?",
    category: "Diagnosis",
  },
  {
    label: "Adrenal Crisis Protocol",
    query: "How should an adrenal crisis be managed immediately?",
    category: "Emergency",
  },
  {
    label: "Sick-Day Rules & Dosing",
    query: "What is sick-day dosing for oral glucocorticoid replacement?",
    category: "Management",
  },
  {
    label: "Steroid Replacement Choices",
    query: "Which glucocorticoid is recommended for adults?",
    category: "Prescribing",
  },
];

export function SearchBox({
  onSearch,
  loading,
  topK,
  onTopKChange,
}: {
  onSearch: (query: string) => void;
  loading: boolean;
  topK: number;
  onTopKChange: (k: number) => void;
}) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut listener for Ctrl+K or /
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function submit(query: string) {
    const trimmed = query.trim();
    if (trimmed.length >= 3 && !loading) onSearch(trimmed);
  }

  return (
    <div className="space-y-4">
      {/* Search Input Bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(value);
        }}
        className="glass-panel relative flex flex-col gap-3 rounded-2xl p-2.5 shadow-xl sm:flex-row"
      >
        <div className="relative flex min-w-0 flex-1 items-center">
          <svg
            className="absolute left-3.5 h-5 w-5 text-ink-faint"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Ask a clinical question about adrenal insufficiency..."
            aria-label="Clinical question"
            className="w-full rounded-xl border border-transparent bg-transparent py-3 pl-11 pr-9 text-base text-ink placeholder:text-ink-faint/80 focus:border-accent-bright/50 focus:bg-surface-2/40 focus:outline-none transition-all"
          />
          {value && (
            <button
              type="button"
              onClick={() => setValue("")}
              className="absolute right-3 rounded-md p-1 text-ink-faint hover:bg-surface-2 hover:text-ink"
              aria-label="Clear input"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Top-K Selector & Action Button */}
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2 rounded-xl border border-line/60 bg-surface-2/70 px-3 py-2.5 text-xs text-ink-dim">
            <span className="font-semibold text-ink-faint uppercase tracking-wider text-[10px]">
              Top-K
            </span>
            <select
              value={topK}
              onChange={(e) => onTopKChange(Number(e.target.value))}
              className="bg-transparent font-mono font-bold text-accent-bright focus:outline-none cursor-pointer"
              aria-label="Number of results"
            >
              {[3, 5, 10, 20].map((k) => (
                <option key={k} value={k} className="bg-surface text-ink">
                  {k} Chunks
                </option>
              ))}
            </select>
          </div>

          <button
            type="submit"
            disabled={loading || value.trim().length < 3}
            className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-accent-deep to-accent px-6 py-3 text-sm font-bold text-ground shadow-lg shadow-accent/20 transition-all hover:brightness-110 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? (
              <>
                <svg className="h-4 w-4 animate-spin text-ground" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Searching...</span>
              </>
            ) : (
              <>
                <span>Retrieve Evidence</span>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Suggested Quick Clinical Queries */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <span className="flex items-center gap-1 text-xs font-semibold text-ink-faint">
          <svg className="h-3.5 w-3.5 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Quick Exemplars:
        </span>
        {CLINICAL_EXAMPLES.map((item) => (
          <button
            key={item.query}
            type="button"
            onClick={() => {
              setValue(item.query);
              submit(item.query);
            }}
            disabled={loading}
            className="group flex items-center gap-1.5 rounded-lg border border-line/70 bg-surface/50 px-3 py-1.5 text-xs text-ink-dim transition-all hover:border-accent-bright/50 hover:bg-surface-2 hover:text-accent-bright disabled:opacity-40"
          >
            <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono text-ink-faint group-hover:text-accent">
              {item.category}
            </span>
            <span>{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
