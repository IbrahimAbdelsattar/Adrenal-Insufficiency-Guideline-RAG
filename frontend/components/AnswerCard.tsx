"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { GenerateResponse } from "@/lib/api";
import { translations, type Language } from "@/lib/translations";
import type { Citation } from "@/lib/api";
import { HighlightMatches } from "@/components/HighlightMatches";
import { CitationMarkers } from "@/components/CitationMarkers";

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

function citationToText(c: Citation): string {
  const loc = [c.section_number ? `§${c.section_number}` : "", c.section_title, c.page_number ? `p.${c.page_number}` : ""]
    .filter(Boolean)
    .join(" · ");
  return `[Source ${c.source_id}] ${c.document_name}${loc ? ` (${loc})` : ""}\n${c.excerpt || c.text || ""}`;
}

const GROUNDING_BADGE_STYLE: Record<string, string> = {
  verified: "text-accent-bright border-accent-bright/40",
  failed: "text-caution border-caution/40",
  abstained: "text-ink-faint border-line/50",
};

export function AnswerCard({ result }: { result: GenerateResponse }) {
  const [lang, setLang] = useState<Language>("en");
  const [highlightedSourceId, setHighlightedSourceId] = useState<string | null>(null);
  const [copiedAnswer, setCopiedAnswer] = useState(false);
  const [copiedEvidence, setCopiedEvidence] = useState(false);
  const {
    query,
    answer,
    citations,
    evidence_found,
    disclaimer,
    latency_ms,
    model,
    cache_hit,
    grounding_status,
  } = result;

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

  const handleCite = (sourceId: string) => {
    setHighlightedSourceId(sourceId);
    requestAnimationFrame(() => {
      setTimeout(() => {
        document
          .querySelector(`[data-answer-citation-anchor="${sourceId}"]`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 40);
    });
    setTimeout(() => {
      setHighlightedSourceId((prev) => (prev === sourceId ? null : prev));
    }, 2200);
  };

  const handleCopyAnswer = () => {
    let out = answer;
    if (citations && citations.length > 0) {
      out += "\n\n---\nSources:\n" + citations.map(citationToText).join("\n\n");
    }
    navigator.clipboard.writeText(out);
    setCopiedAnswer(true);
    setTimeout(() => setCopiedAnswer(false), 2000);
  };

  const handleCopyEvidenceOnly = () => {
    const out = (citations || []).map(citationToText).join("\n\n---\n\n");
    navigator.clipboard.writeText(out);
    setCopiedEvidence(true);
    setTimeout(() => setCopiedEvidence(false), 2000);
  };

  const groundingLabel =
    grounding_status === "failed"
      ? t.groundingFailedBadge || "Unverified"
      : grounding_status === "abstained"
        ? t.groundingAbstainedBadge || "No Answer"
        : t.groundingVerifiedBadge || "Verified";

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

        {/* Quality & Risk Badges */}
        <div className="flex flex-wrap items-center gap-2">
          {result.risk_assessment && (
            <span
              className={`mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider ${
                result.risk_assessment.is_emergency
                  ? "border-red-500/60 text-red-500 bg-red-500/10 animate-pulse"
                  : result.risk_assessment.tier === "sick_day_stress"
                    ? "border-amber-500/60 text-amber-500 bg-amber-500/10"
                    : result.risk_assessment.tier === "pediatric_specialist"
                      ? "border-sky-500/60 text-sky-500 bg-sky-500/10"
                      : "border-line/60 text-ink-dim"
              }`}
            >
              {result.risk_assessment.is_emergency ? "🚨 EMERGENCY" : result.risk_assessment.tier.replace(/_/g, " ")}
            </span>
          )}
          {!evidence_found && (
            <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-caution border-caution/40">
              {t.insufficientEvidenceBadge || "Insufficient Evidence"}
            </span>
          )}
          {answer && grounding_status && (
            <span
              className={`mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider ${
                GROUNDING_BADGE_STYLE[grounding_status] || GROUNDING_BADGE_STYLE.verified
              }`}
              title={
                grounding_status === "verified"
                  ? "Every clinical claim resolved to a cited passage"
                  : grounding_status === "failed"
                    ? "Grounding could not be verified; answer withheld"
                    : "No answer was generated"
              }
            >
              {groundingLabel}
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

      {/* Clinical Risk / Emergency Triage Alert */}
      {result.risk_assessment?.is_emergency && (
        <div className="mb-5 rounded-xl border border-red-500/50 bg-red-500/10 p-4 text-red-600 dark:text-red-400 animate-in fade-in duration-300">
          <div className="flex items-center gap-2 font-bold text-xs sm:text-sm">
            <span className="flex h-2.5 w-2.5 rounded-full bg-red-500 animate-ping" />
            {result.risk_assessment.safety_banner || "CRITICAL EMERGENCY ALERT: Suspected Acute Adrenal Crisis"}
          </div>
          {result.risk_assessment.recommended_triage_action && (
            <p className="mt-1.5 text-xs text-ink/80 leading-relaxed font-medium">
              {result.risk_assessment.recommended_triage_action}
            </p>
          )}
        </div>
      )}

      {result.risk_assessment?.safety_banner && !result.risk_assessment.is_emergency && (
        <div className="mb-4 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-amber-700 dark:text-amber-300">
          <div className="font-semibold text-xs sm:text-sm flex items-center gap-2">
            <span>{result.risk_assessment.safety_banner}</span>
          </div>
        </div>
      )}

      {/* Answer Body */}
      <div className="answer-markdown text-ink leading-relaxed mb-6 text-sm sm:text-base">
        {answer ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h3 className="mb-3 mt-6 text-xl font-bold first:mt-0"><CitationMarkers onCite={handleCite}><HighlightMatches query={query}>{children}</HighlightMatches></CitationMarkers></h3>,
              h2: ({ children }) => <h4 className="mb-3 mt-5 text-lg font-bold first:mt-0"><CitationMarkers onCite={handleCite}><HighlightMatches query={query}>{children}</HighlightMatches></CitationMarkers></h4>,
              h3: ({ children }) => <h5 className="mb-2 mt-4 text-base font-bold first:mt-0"><CitationMarkers onCite={handleCite}><HighlightMatches query={query}>{children}</HighlightMatches></CitationMarkers></h5>,
              p: ({ children }) => <p className="mb-3 last:mb-0"><CitationMarkers onCite={handleCite}><HighlightMatches query={query}>{children}</HighlightMatches></CitationMarkers></p>,
              ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
              ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
              li: ({ children }) => <li className="pl-1"><CitationMarkers onCite={handleCite}>{children}</CitationMarkers></li>,
              blockquote: ({ children }) => (
                <blockquote className="mb-3 border-l-2 border-accent-bright/60 pl-4 text-ink-dim"><CitationMarkers onCite={handleCite}><HighlightMatches query={query}>{children}</HighlightMatches></CitationMarkers></blockquote>
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
              th: ({ children }) => <th className="border-b border-line/60 bg-ink/5 px-3 py-2 font-bold"><CitationMarkers onCite={handleCite}><HighlightMatches query={query}>{children}</HighlightMatches></CitationMarkers></th>,
              td: ({ children }) => <td className="border-b border-line/40 px-3 py-2 align-top last:border-b-0"><CitationMarkers onCite={handleCite}><HighlightMatches query={query}>{children}</HighlightMatches></CitationMarkers></td>,
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
          <ul className="flex flex-col gap-3">
            {citations.map((c, i) => {
              const textContent = c.text || c.excerpt || "";
              const isHighlighted = highlightedSourceId === c.source_id;
              const isWeak = Boolean(c.below_floor);
              return (
                <li
                  key={`${c.source_id}-${i}`}
                  data-answer-citation-anchor={c.source_id}
                  className={`mono-card rounded-xl p-3.5 text-xs text-ink-dim border space-y-2 transition-all duration-300 ${
                    isHighlighted
                      ? "ring-2 ring-accent-bright border-accent-bright/60 bg-accent-bright/10"
                      : isWeak
                        ? "border-dashed border-caution/50"
                        : "border-line/50"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/30 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="mono-pill px-2 py-0.5 font-mono text-[11px] font-extrabold text-accent-bright">
                        [{c.source_id}]
                      </span>
                      <div>
                        <span className="font-bold text-ink text-[12px]">{c.document_name}</span>
                        <span className="text-xs text-ink-faint ml-1.5">
                          {formatSection(c)}
                          {c.page_number && ` · Page ${c.page_number}`}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {c.absolute_relevance !== undefined && (
                        <span
                          className="font-mono text-[10px] text-ink-dim mono-inset px-2 py-0.5 rounded"
                          title={t.retrievalScoreHint || "Ranking signal only — not clinical confidence"}
                        >
                          {t.relevanceScore || "Retrieval Score"}: {Math.round(c.absolute_relevance * 100)}%
                        </span>
                      )}
                      {c.source_url && (
                        <a
                          href={c.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-accent-bright hover:underline text-[11px] font-bold"
                        >
                          NICE ↗
                        </a>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                    <span
                      className={`mono-pill px-2 py-0.5 font-bold uppercase tracking-wide ${
                        c.resolved_by === "recommendation_id"
                          ? "text-ink-faint border-line/50"
                          : "text-accent-bright border-accent-bright/40"
                      }`}
                    >
                      {c.resolved_by === "recommendation_id"
                        ? t.relatedRecommendation || "Related Recommendation"
                        : t.directCitation || "Direct Citation"}
                    </span>
                    {isWeak && (
                      <span className="mono-pill px-2 py-0.5 font-bold uppercase tracking-wide text-caution border-caution/40">
                        {t.weakMatchBadge || "Weak Match"}
                      </span>
                    )}
                    {c.publication_year ? (
                      <span className="text-ink-faint">
                        {t.publishedLabel || "Published"} {c.publication_year}
                      </span>
                    ) : null}
                  </div>

                  {textContent && (
                    <div className="text-[12px] leading-relaxed text-ink-dim bg-ink/5 p-2.5 rounded-lg border border-line/30 font-sans">
                      <HighlightMatches query={query}>{textContent}</HighlightMatches>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Copy Actions */}
      {answer && (
        <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-line/60 pt-4">
          {citations && citations.length > 0 && (
            <button
              type="button"
              onClick={handleCopyEvidenceOnly}
              className="mono-button px-3 py-1.5 rounded-xl text-xs font-bold text-ink-dim hover:text-ink transition-all cursor-pointer"
            >
              {copiedEvidence ? `✓ ${t.copiedAllEvidence || "All Evidence Copied!"}` : `📄 ${t.copyAllEvidence || "Copy All Evidence"}`}
            </button>
          )}
          <button
            type="button"
            onClick={handleCopyAnswer}
            className="mono-button px-3 py-1.5 rounded-xl text-xs font-bold text-ink-dim hover:text-ink transition-all cursor-pointer"
          >
            {copiedAnswer
              ? `✓ ${t.copied || "Copied!"}`
              : `📋 ${citations && citations.length > 0 ? t.copyWithCitations || "Copy Answer + Citations" : t.copyAnswer || "Copy"}`}
          </button>
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
