"use client";

import { useState, useEffect } from "react";
import type { GenerateResponse } from "@/lib/api";
import { translations, type Language } from "@/lib/translations";

export function AnswerCard({ result }: { result: GenerateResponse }) {
  const [lang, setLang] = useState<Language>("en");
  const { answer, citations, evidence_found, disclaimer, latency_ms, model } = result;

  useEffect(() => {
    const savedLang = localStorage.getItem("eva_lang") as Language | null;
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

  return (
    <article
      className="mono-card-interactive relative rounded-2xl p-6"
    >
      {/* Monomorphic Eva AI Header */}
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-surface-divider pb-4">
        <div className="flex items-center gap-3">
          {/* AI Icon Badge */}
          <span className="mono-card flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-mono text-xs font-extrabold text-accent-bright border border-accent-bright/20">
            AI
          </span>
          <h2 className="text-lg font-bold text-ink-strong">{t.aiAnswerLabel || "AI Answer"}</h2>
        </div>

        {/* Quality Badges */}
        <div className="flex flex-wrap items-center gap-2">
          {!evidence_found && (
            <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-caution border-caution/40">
              {t.insufficientEvidenceBadge || "Insufficient Evidence"}
            </span>
          )}
          <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-ink-dim">
            {latency_ms}ms
          </span>
          <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-ink-dim">
            {model.split("/").pop()}
          </span>
        </div>
      </header>

      {/* Answer Body */}
      <div className="prose prose-sm md:prose-base dark:prose-invert max-w-none text-ink-main leading-relaxed mb-6 whitespace-pre-wrap">
        {answer}
      </div>

      {/* Citations Footer */}
      {citations && citations.length > 0 && (
        <div className="mt-6 border-t border-surface-divider pt-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-ink-dim mb-3">
            {t.citationsLabel || "Sources cited"}
          </h3>
          <ul className="flex flex-col gap-2">
            {citations.map((c, i) => (
              <li key={`${c.source_id}-${i}`} className="mono-inset flex items-start gap-3 rounded-xl px-4 py-3 text-sm text-ink-dim">
                <span className="font-mono text-xs font-bold text-accent-bright mt-0.5">
                  [{c.source_id}]
                </span>
                <div className="flex flex-col">
                  <span className="font-semibold text-ink-main">{c.document_name}</span>
                  <span className="text-xs mt-0.5">
                    {c.section_title ? `${c.section_number} ${c.section_title}` : c.section_number}
                    {c.page_number && ` (Page ${c.page_number})`}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Disclaimer */}
      {disclaimer && (
        <div className="mt-6 rounded-xl bg-surface-raised p-4 text-xs italic text-ink-dim">
          {disclaimer}
        </div>
      )}
    </article>
  );
}
