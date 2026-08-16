"use client";

import { useState } from "react";
import type { RetrievalResult } from "@/lib/api";

const EXCERPT_CHARS = 340;

function getScoreMeterClass(score: number, belowFloor: boolean) {
  if (belowFloor) return "meter-low";
  if (score >= 0.75) return "meter-high";
  return "meter-medium";
}

function getScoreTone(score: number, belowFloor: boolean) {
  if (belowFloor) return "text-weak";
  if (score >= 0.75) return "text-accent-bright font-bold";
  return "text-cyan-400 font-semibold";
}

export function ChunkCard({ result }: { result: RetrievalResult }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const { chunk, score, rank, below_floor: belowFloor } = result;

  const isLong = chunk.text.length > EXCERPT_CHARS;
  const body =
    expanded || !isLong ? chunk.text : `${chunk.text.slice(0, EXCERPT_CHARS)}…`;

  const recommendations = chunk.recommendation_ids
    .split(",")
    .filter(Boolean);

  function copyCitation() {
    const citation = `[Source: ${chunk.document_name}, Page ${chunk.page_number}, Section: "${chunk.section_title}"${
      recommendations.length > 0 ? `, Rec ${recommendations.join(", ")}` : ""
    }]`;
    navigator.clipboard.writeText(`${citation}\n"${chunk.text}"`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <article
      className={`glass-panel-interactive relative rounded-2xl p-6 transition-all ${
        belowFloor
          ? "border-line/40 opacity-75"
          : "border-line/80 hover:border-accent-bright/40"
      }`}
    >
      {/* Top Header: Rank Badge, Relevance Gauge, Status Flags */}
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-surface-2 font-mono text-xs font-bold text-accent-bright border border-line">
            #{rank}
          </span>

          {/* Relevance Score Gauge Bar */}
          <div className="flex items-center gap-2.5 rounded-xl border border-line/60 bg-surface-2/60 px-3 py-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
              Relevance Score
            </span>
            <div className="h-2 w-24 overflow-hidden rounded-full bg-surface-2">
              <div
                className={`h-full transition-all duration-500 ${getScoreMeterClass(score, belowFloor)}`}
                style={{ width: `${Math.min(100, Math.max(5, Math.round(score * 100)))}%` }}
              />
            </div>
            <span className={`font-mono text-xs tabular-nums ${getScoreTone(score, belowFloor)}`}>
              {(score * 100).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Quality Badges */}
        <div className="flex flex-wrap items-center gap-2">
          {belowFloor && (
            <span className="rounded-lg border border-caution/40 bg-caution/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-caution">
              Below Relevance Floor
            </span>
          )}
          {chunk.requires_caution && (
            <span className="rounded-lg border border-caution/50 bg-caution/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-caution">
              Non-Current Source
            </span>
          )}
          {chunk.is_oversized && (
            <span className="rounded-lg border border-line bg-surface-2 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-ink-faint">
              Oversized Recommendation
            </span>
          )}

          {/* Copy Citation Quick Button */}
          <button
            type="button"
            onClick={copyCitation}
            className="flex items-center gap-1.5 rounded-lg border border-line/80 bg-surface-2/80 px-2.5 py-1 text-xs font-medium text-ink-dim transition-colors hover:border-accent-bright/50 hover:text-accent-bright"
            title="Copy formatted citation string"
          >
            {copied ? (
              <>
                <svg className="h-3.5 w-3.5 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-accent-bright font-semibold">Copied!</span>
              </>
            ) : (
              <>
                <svg className="h-3.5 w-3.5 text-ink-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                </svg>
                <span>Cite</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* Provenance Banner (Section & Page Attribution) */}
      <div className="mb-4 rounded-xl border-l-4 border-accent-bright bg-surface-2/40 p-3.5">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
          <p className="text-sm font-bold text-ink">
            {chunk.section_title || "Untitled section"}
          </p>
        </div>

        {chunk.subsection_title && (
          <p className="mt-1 text-xs font-semibold text-accent-bright/90 pl-6">
            ↳ {chunk.subsection_title}
          </p>
        )}

        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 pl-6 text-xs text-ink-faint">
          <a
            href={chunk.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="font-medium text-ink-dim underline decoration-dotted underline-offset-2 hover:text-accent-bright"
          >
            {chunk.document_name}
          </a>
          <span aria-hidden>·</span>
          <span className="rounded bg-surface px-2 py-0.5 font-mono text-[11px] font-semibold text-ink-dim border border-line">
            Page {chunk.page_number}
          </span>
          <span aria-hidden>·</span>
          <span>{chunk.publication_year}</span>
          {recommendations.length > 0 && (
            <>
              <span aria-hidden>·</span>
              <span className="rounded bg-accent-deep/20 px-2 py-0.5 font-mono text-[11px] font-bold text-accent-bright border border-accent-bright/30">
                Rec {recommendations.join(", ")}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Chunk Evidence Text */}
      <div className="relative">
        <p className="whitespace-pre-line text-sm leading-relaxed text-ink/90 font-normal">
          {body}
        </p>
      </div>

      {/* Card Footer: Expand toggle & ID badge */}
      <footer className="mt-4 flex items-center justify-between border-t border-line/60 pt-3">
        {isLong ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-xs font-bold text-accent-bright hover:underline"
          >
            <span>{expanded ? "Show Excerpt" : "Show Full Chunk"}</span>
            <svg
              className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        ) : (
          <div />
        )}

        <div className="flex items-center gap-2 font-mono text-[11px] text-ink-faint">
          <span className="rounded bg-surface-2 px-2 py-0.5 border border-line/60">{chunk.chunk_id}</span>
          <span>·</span>
          <span>{chunk.token_count} tok</span>
        </div>
      </footer>
    </article>
  );
}
