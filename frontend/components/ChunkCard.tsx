"use client";

import { useState, useEffect } from "react";
import type { RetrievalResult } from "@/lib/api";
import { translations, type Language } from "@/lib/translations";

const EXCERPT_CHARS = 340;

function getScoreMeterClass(score: number, belowFloor: boolean) {
  if (belowFloor) return "meter-low";
  if (score >= 0.75) return "meter-high";
  return "meter-medium";
}

function getScoreTone(score: number, belowFloor: boolean) {
  if (belowFloor) return "text-weak";
  if (score >= 0.75) return "text-accent-bright font-bold";
  return "text-ink-dim font-semibold";
}

export function ChunkCard({ result }: { result: RetrievalResult }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [lang, setLang] = useState<Language>("en");
  const { chunk, score, rank, below_floor: belowFloor } = result;

  useEffect(() => {
    const savedLang = (localStorage.getItem("eva_lang") || localStorage.getItem("sapphire_lang")) as Language | null;
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

  const isLong = chunk.text.length > EXCERPT_CHARS;
  const body =
    expanded || !isLong ? chunk.text : `${chunk.text.slice(0, EXCERPT_CHARS)}…`;

  const recommendations = chunk.recommendation_ids
    .split(",")
    .filter(Boolean);

  function copyCitation() {
    const citation = `[${t.disclaimerTitle} ${chunk.document_name}, ${t.pagePrefix} ${chunk.page_number}, ${chunk.section_title}${
      recommendations.length > 0 ? `, ${t.recPrefix} ${recommendations.join(", ")}` : ""
    }]`;
    navigator.clipboard.writeText(`${citation}\n"${chunk.text}"`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <article
      className={`mono-card-interactive relative rounded-2xl p-6 ${
        belowFloor ? "opacity-75" : ""
      }`}
    >
      {/* Monomorphic Eva AI Header */}
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {/* Monomorphic Extruded Rank Badge */}
          <span className="mono-card flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-mono text-xs font-extrabold text-accent-bright border border-accent-bright/20">
            {t.rankPrefix}{rank}
          </span>

          {/* Monomorphic Debossed Score Gauge */}
          <div className="mono-inset flex items-center gap-2.5 rounded-xl px-3.5 py-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">
              {t.metricLabel}
            </span>
            <div className="mono-inset h-2 w-24 overflow-hidden rounded-full p-0.5">
              <div
                className={`h-full rounded-full transition-all duration-500 ${getScoreMeterClass(score, belowFloor)}`}
                style={{ width: `${Math.min(100, Math.max(5, Math.round(score * 100)))}%` }}
              />
            </div>
            <span className={`font-mono text-xs tabular-nums ${getScoreTone(score, belowFloor)}`}>
              {(score * 100).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Quality Badges & Tactile Copy Citation Button */}
        <div className="flex flex-wrap items-center gap-2">
          {belowFloor && (
            <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-caution border-caution/40">
              {t.belowFloorBadge}
            </span>
          )}
          {chunk.requires_caution && (
            <span className="mono-pill px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-caution border-caution/40">
              {t.cautionBadge}
            </span>
          )}
          {chunk.is_oversized && (
            <span className="mono-pill px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-ink-faint">
              {t.oversizedBadge}
            </span>
          )}

          {/* Monomorphic Tactile Copy Button */}
          <button
            type="button"
            onClick={copyCitation}
            className="mono-button flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-ink-dim cursor-pointer"
            title="Copy citation snippet"
          >
            {copied ? (
              <>
                <svg className="h-3.5 w-3.5 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-accent-bright">{t.copiedBtn}</span>
              </>
            ) : (
              <>
                <svg className="h-3.5 w-3.5 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                </svg>
                <span>{t.citeBtn}</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* Monomorphic Eva AI Section Banner */}
      <div className="mono-inset mb-4 rounded-xl border-s-4 border-accent-bright p-4">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-accent-bright shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
          <p className="text-sm font-extrabold text-ink">
            {chunk.section_title || "Untitled section"}
          </p>
        </div>

        {chunk.subsection_title && (
          <p className="mt-1 text-xs font-semibold text-accent-bright/90 ps-6">
            ↳ {chunk.subsection_title}
          </p>
        )}

        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 ps-6 text-xs text-ink-faint">
          <a
            href={chunk.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="font-semibold text-ink-dim underline decoration-dotted underline-offset-2 hover:text-accent-bright"
          >
            {chunk.document_name}
          </a>
          <span aria-hidden>·</span>
          <span className="mono-pill px-2 py-0.5 font-mono text-[11px] font-bold text-accent-bright">
            {t.pagePrefix} {chunk.page_number}
          </span>
          <span aria-hidden>·</span>
          <span>{chunk.publication_year}</span>
          {recommendations.length > 0 && (
            <>
              <span aria-hidden>·</span>
              <span className="mono-inset px-2 py-0.5 font-mono text-[11px] font-extrabold text-accent-bright rounded-md border border-accent-bright/30">
                {t.recPrefix} {recommendations.join(", ")}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Chunk Prose Body */}
      <p className="whitespace-pre-line text-sm leading-relaxed text-ink/90 font-normal">
        {body}
      </p>

      {/* Card Footer */}
      <footer className="mt-4 flex items-center justify-between border-t border-line/60 pt-3.5">
        {isLong ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mono-button flex items-center gap-1.5 rounded-xl px-3 py-1 text-xs font-extrabold text-accent-bright cursor-pointer"
          >
            <span>{expanded ? t.showExcerpt : t.showFull}</span>
            <svg
              className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        ) : (
          <div />
        )}

        <div className="flex items-center gap-2 font-mono text-[11px] text-ink-faint">
          <span className="mono-inset px-2 py-0.5 rounded-md font-semibold text-accent-bright">{chunk.chunk_id}</span>
          <span>·</span>
          <span>{chunk.token_count} {t.tokSuffix}</span>
        </div>
      </footer>
    </article>
  );
}
