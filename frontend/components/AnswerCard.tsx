"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
      <div className="answer-markdown text-ink leading-relaxed mb-6 text-sm sm:text-base">
        {answer ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h3 className="mb-3 mt-6 text-xl font-bold first:mt-0">{children}</h3>,
              h2: ({ children }) => <h4 className="mb-3 mt-5 text-lg font-bold first:mt-0">{children}</h4>,
              h3: ({ children }) => <h5 className="mb-2 mt-4 text-base font-bold first:mt-0">{children}</h5>,
              p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
              ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
              ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
              li: ({ children }) => <li className="pl-1">{children}</li>,
              blockquote: ({ children }) => (
                <blockquote className="mb-3 border-l-2 border-accent-bright/60 pl-4 text-ink-dim">{children}</blockquote>
              ),
              strong: ({ children }) => <strong className="font-bold text-ink">{children}</strong>,
              em: ({ children }) => <em>{children}</em>,
              code: ({ children }) => (
                <code className="rounded bg-ink/10 px-1.5 py-0.5 font-mono text-[0.9em] break-words">{children}</code>
              ),
              pre: ({ children }) => (
                <pre className="mb-3 overflow-x-auto rounded-xl bg-ink/10 p-4 font-mono text-xs leading-relaxed">{children}</pre>
              ),
              a: ({ children, href }) => (
                <a
                  className="break-words text-accent-bright underline underline-offset-2"
                  href={href}
                  rel="noreferrer"
                  target="_blank"
                >
                  {children}
                </a>
              ),
              table: ({ children }) => (
                <div className="mb-3 overflow-x-auto rounded-xl border border-line/60">
                  <table className="min-w-full border-collapse text-left text-sm">{children}</table>
                </div>
              ),
              th: ({ children }) => <th className="border-b border-line/60 bg-ink/5 px-3 py-2 font-bold">{children}</th>,
              td: ({ children }) => <td className="border-b border-line/40 px-3 py-2 align-top last:border-b-0">{children}</td>,
              hr: () => <hr className="my-4 border-line/60" />,
            }}
          >
            {answer}
          </ReactMarkdown>
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
