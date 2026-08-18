"use client";

import { useState, useEffect } from "react";
import type { GenerateResponse } from "@/lib/api";
import { translations, type Language } from "@/lib/translations";
import type { Citation } from "@/lib/api";

/**
 * Render "1.7 Emergency management of adrenal crisis" from a citation.
 *
 * The sectioner stores section_title with its number already prefixed, so
 * naively joining number + title prints "1.7 1.7 Emergency management ...".
 */
function formatSection(c: Citation): string {
  const number = c.section_number?.trim() ?? "";
  const title = c.section_title?.trim() ?? "";
  if (!title) return number;
  if (!number || title.startsWith(number)) return title;
  return `${number} ${title}`;
}

export function AnswerCard({ result }: { result: GenerateResponse }) {
  const [lang, setLang] = useState<Language>("en");
  const { answer, citations, evidence_found, disclaimer, latency_ms, model, cache_hit } = result;

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

  const modelName = (model || "gemini").split("/").pop();

  return (
    <article
      className="mono-card-interactive relative rounded-2xl p-6"
    >
      {/* Monomorphic Eva AI Header */}
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-line/60 pb-4">
        <div className="flex items-center gap-3">
          {/* AI Icon Badge */}
          <span className="mono-card flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-mono text-xs font-extrabold text-accent-bright border border-accent-bright/20">
            AI
          </span>
          <h2 className="text-lg font-bold text-ink">{t.aiAnswerLabel || "AI Answer"}</h2>
        </div>

        {/* Quality Badges */}
        <div className="flex flex-wrap items-center gap-2">
          {!evidence_found && (
            <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-caution border-caution/40">
              {t.insufficientEvidenceBadge || "Insufficient Evidence"}
            </span>
          )}
          {cache_hit && (
            <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-accent-bright border-accent-bright/40">
              cached
            </span>
          )}
          {latency_ms > 0 && (
            <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-ink-dim font-mono">
              ⚡ {latency_ms}ms
            </span>
          )}
          <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-ink-dim font-mono">
            {modelName}
          </span>
        </div>
      </header>

      {/* Answer Body */}
      <div className="text-ink leading-relaxed mb-6 whitespace-pre-wrap text-sm sm:text-base">
        {answer ? (
          answer
        ) : (
          <div className="flex items-center gap-2 text-ink-dim py-4 text-sm animate-pulse">
            <span className="h-2 w-2 rounded-full bg-accent-bright animate-mono-pulse" />
            <span>{t.generatingBtn || "Synthesizing clinical response..."}</span>
          </div>
        )}
      </div>

      {/* Citations Footer */}
      {citations && citations.length > 0 && (
        <div className="mt-6 border-t border-line/60 pt-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-ink-faint mb-3">
            {t.citationsLabel || "Sources cited"}
          </h3>
          <ul className="flex flex-col gap-2">
            {citations.map((c, i) => (
              <li key={`${c.source_id}-${i}`} className="mono-inset flex items-start gap-3 rounded-xl px-4 py-3 text-sm text-ink-dim">
                <span className="font-mono text-xs font-bold text-accent-bright mt-0.5">
                  [{c.source_id}]
                </span>
                <div className="flex flex-col">
                  <span className="font-semibold text-ink">{c.document_name}</span>
                  <span className="text-xs mt-0.5 text-ink-faint">
                    {formatSection(c)}
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
        <div className="mt-6 rounded-xl mono-inset p-4 text-xs italic text-ink-dim border border-line/40">
          {disclaimer}
        </div>
      )}
    </article>
  );
}
