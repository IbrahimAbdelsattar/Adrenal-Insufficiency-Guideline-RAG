"use client";

import { useState, useEffect, useRef } from "react";
import { translations, type Language } from "@/lib/translations";

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
  const [lang, setLang] = useState<Language>("en");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const savedLang = localStorage.getItem("sapphire_lang") as Language | null;
    if (savedLang && (savedLang === "en" || savedLang === "ar")) {
      setLang(savedLang);
    }
    const handleLangChange = (e: Event) => {
      const customEvent = e as CustomEvent<Language>;
      if (customEvent.detail) setLang(customEvent.detail);
    };
    window.addEventListener("languageChange", handleLangChange);
    return () => window.removeEventListener("languageChange", handleLangChange);
  }, []);

  const t = translations[lang];

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
      {/* Sapphire VEIL Monomorphic Search Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(value);
        }}
        className="mono-card relative flex flex-col gap-3 rounded-2xl p-3 sm:flex-row"
      >
        <div className="mono-inset mono-inset-active relative flex min-w-0 flex-1 items-center rounded-xl transition-all">
          <svg
            className="absolute ms-3.5 h-5 w-5 text-accent-bright"
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
            placeholder={t.searchPlaceholder}
            aria-label="Clinical question"
            className="w-full rounded-xl border-none bg-transparent py-3.5 ps-11 pe-10 text-base text-ink placeholder:text-ink-faint/70 focus:outline-none"
          />
          {value && (
            <button
              type="button"
              onClick={() => setValue("")}
              className="mono-button absolute me-3 end-0 rounded-lg p-1.5 text-ink-faint hover:text-ink cursor-pointer"
              aria-label="Clear input"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Top-K Selector & Primary Sapphire Button */}
        <div className="flex items-center gap-2.5">
          <div className="mono-inset flex items-center gap-2 rounded-xl px-3 py-2.5 text-xs text-ink-dim">
            <span className="font-mono text-[10px] font-bold text-ink-faint uppercase tracking-wider">
              {t.topKLabel}
            </span>
            <select
              value={topK}
              onChange={(e) => onTopKChange(Number(e.target.value))}
              className="bg-transparent font-mono font-bold text-accent-bright focus:outline-none cursor-pointer"
              aria-label="Number of results"
            >
              {[3, 5, 10, 20].map((k) => (
                <option key={k} value={k} className="bg-surface text-ink">
                  {k} {t.chunksSuffix}
                </option>
              ))}
            </select>
          </div>

          <button
            type="submit"
            disabled={loading || value.trim().length < 3}
            className="mono-button-primary flex items-center justify-center gap-2 rounded-xl px-6 py-3.5 text-sm font-extrabold text-white cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? (
              <>
                <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>{t.searchingBtn}</span>
              </>
            ) : (
              <>
                <span>{t.retrieveBtn}</span>
                <svg className={`h-4 w-4 ${lang === "ar" ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Sapphire VEIL Exemplar Chips */}
      <div className="flex flex-wrap items-center gap-2.5 pt-1">
        <span className="flex items-center gap-1.5 text-xs font-bold text-ink-faint">
          <svg className="h-3.5 w-3.5 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          {t.quickExemplars}
        </span>
        {t.exemplars.map((item) => (
          <button
            key={item.query}
            type="button"
            onClick={() => {
              setValue(item.query);
              submit(item.query);
            }}
            disabled={loading}
            className="mono-button group flex items-center gap-2 rounded-xl px-3.5 py-1.5 text-xs text-ink-dim cursor-pointer disabled:opacity-40"
          >
            <span className="mono-inset px-2 py-0.5 text-[10px] font-mono font-bold text-accent-bright rounded-md">
              {item.category}
            </span>
            <span className="font-medium group-hover:text-accent-bright transition-colors">{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
