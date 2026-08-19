"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "@/lib/api";
import { HighlightMatches } from "@/components/HighlightMatches";

interface EvidencePanelProps {
  citations: Citation[];
  query: string;
  isExpanded: boolean;
  onToggleExpand: () => void;
  copiedEvidenceId: string | null;
  onCopyEvidence: (id: string, text: string) => void;
  fullTextCitationMap: Record<string, boolean>;
  onToggleFullText: (citationKey: string) => void;
  t: Record<string, unknown>;
  msgId: string;
  highlightedCitationKey?: string | null;
}

function formatRetrievedAt(iso: string | undefined): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return null;
  }
}

export function EvidencePanel({
  citations,
  query,
  isExpanded,
  onToggleExpand,
  copiedEvidenceId,
  onCopyEvidence,
  fullTextCitationMap,
  onToggleFullText,
  t,
  msgId,
  highlightedCitationKey,
}: EvidencePanelProps) {
  if (!citations || citations.length === 0) return null;

  const typedT = t as Record<string, string>;

  return (
    <div className="mt-4 border-t border-line/40 pt-3 space-y-2.5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-extrabold uppercase tracking-wider text-ink-faint flex items-center gap-1.5">
          <span>{typedT.citationsLabel || "Evidence Sources:"}</span>
          <span className="mono-pill px-1.5 py-0.2 text-[9px] font-mono font-extrabold text-accent-bright">
            {citations.length}
          </span>
        </div>
        <button
          type="button"
          onClick={onToggleExpand}
          className="mono-button flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold text-accent-bright hover:text-accent-bright/80 transition-all cursor-pointer"
        >
          <span>{isExpanded ? "▲" : "▼"}</span>
          <span>
            {isExpanded
              ? typedT.hideEvidence || "Hide Evidence"
              : typedT.viewEvidence || "View Retrieved Evidence"}
          </span>
        </button>
      </div>

      {/* Collapsed: Quick Chips */}
      {!isExpanded && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {citations.map((c, idx) => (
            <div
              key={idx}
              className="mono-card flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] text-ink-dim border border-line/40"
            >
              <span className="font-mono font-extrabold text-accent-bright">
                [{c.source_id}]
              </span>
              <span className="font-semibold text-ink">{c.document_name}</span>
              {c.page_number ? (
                <span className="text-ink-faint">· p.{c.page_number}</span>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {/* Expanded: Full Evidence Inspector */}
      {isExpanded && (
        <div className="space-y-3 pt-2 animate-fade-in-up">
          {citations.map((c, idx) => {
            const citationKey = `${msgId}-${c.source_id}-${idx}`;
            const anchorKey = `${msgId}-${c.source_id}`;
            const isConcise = Boolean(fullTextCitationMap[citationKey]);
            const displayText = isConcise && c.excerpt ? c.excerpt : (c.text || c.excerpt || "");
            const isHighlighted = highlightedCitationKey === anchorKey;
            const isWeak = Boolean(c.below_floor);
            const retrievedAt = formatRetrievedAt(c.retrieved_at);

            return (
              <div
                key={idx}
                data-citation-anchor={anchorKey}
                className={`mono-card rounded-xl p-3 text-xs space-y-2 border transition-all duration-300 ${
                  isHighlighted
                    ? "ring-2 ring-accent-bright border-accent-bright/60 bg-accent-bright/10"
                    : isWeak
                      ? "border-dashed border-caution/50 bg-card/60"
                      : "border-accent-bright/20 bg-card/60"
                }`}
              >
                {/* Evidence Header */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/30 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="mono-pill px-2 py-0.5 font-mono text-[11px] font-extrabold text-accent-bright">
                      [Source {c.source_id}]
                    </span>
                    <div>
                      <span className="font-bold text-ink text-[12px]">
                        {c.document_name}
                      </span>
                      <span className="text-ink-faint text-[11px] ml-1.5">
                        {c.section_number ? `§${c.section_number} ` : ""}
                        {c.section_title}
                        {c.page_number ? ` · Page ${c.page_number}` : ""}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {c.absolute_relevance !== undefined && (
                      <span
                        className="font-mono text-[10px] text-ink-dim mono-inset px-2 py-0.5 rounded"
                        title={typedT.retrievalScoreHint || "Ranking signal only — not clinical confidence"}
                      >
                        {typedT.relevanceScore || "Retrieval Score"}: {Math.round(c.absolute_relevance * 100)}%
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

                {/* Provenance Badges: citation kind, weak match, source metadata */}
                <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                  <span
                    className={`mono-pill px-2 py-0.5 font-bold uppercase tracking-wide ${
                      c.resolved_by === "recommendation_id"
                        ? "text-ink-faint border-line/50"
                        : "text-accent-bright border-accent-bright/40"
                    }`}
                    title={
                      c.resolved_by === "recommendation_id"
                        ? "The model cited the guideline's own numbering; resolved to this chunk but not validated against one specific sentence"
                        : "The model cited this source marker directly against the claim above"
                    }
                  >
                    {c.resolved_by === "recommendation_id"
                      ? typedT.relatedRecommendation || "Related Recommendation"
                      : typedT.directCitation || "Direct Citation"}
                  </span>
                  {isWeak && (
                    <span className="mono-pill px-2 py-0.5 font-bold uppercase tracking-wide text-caution border-caution/40">
                      {typedT.weakMatchBadge || "Weak Match"}
                    </span>
                  )}
                  {c.requires_caution && (
                    <span className="mono-pill px-2 py-0.5 font-bold uppercase tracking-wide text-caution border-caution/40">
                      {typedT.cautionBadge || "Non-Current Source"}
                    </span>
                  )}
                  {c.publication_year ? (
                    <span className="text-ink-faint">
                      {typedT.publishedLabel || "Published"} {c.publication_year}
                    </span>
                  ) : null}
                  {retrievedAt && (
                    <span className="text-ink-faint">
                      · {typedT.retrievedLabel || "Retrieved"} {retrievedAt}
                    </span>
                  )}
                </div>

                {/* Evidence Text */}
                <div className="text-[12px] leading-relaxed text-ink-dim bg-ink/5 p-2.5 rounded-lg border border-line/30 font-sans">
                  <HighlightMatches query={query}>{displayText}</HighlightMatches>
                </div>

                {/* Action Controls */}
                <div className="flex items-center justify-between pt-1 text-[11px]">
                  {c.text && c.text.length > (c.excerpt?.length || 0) ? (
                    <button
                      type="button"
                      onClick={() => onToggleFullText(citationKey)}
                      className="text-accent-bright hover:underline font-semibold cursor-pointer"
                    >
                      {isConcise
                        ? `▼ ${typedT.fullGuidelineText || "Show Full Guideline Chunk Text"}`
                        : `▲ ${typedT.conciseExcerpt || "Show Concise Excerpt"}`}
                    </button>
                  ) : (
                    <div />
                  )}
                  <button
                    type="button"
                    onClick={() => onCopyEvidence(citationKey, displayText)}
                    className="mono-button px-2 py-0.5 rounded text-[10px] text-ink-dim hover:text-ink transition-all cursor-pointer"
                  >
                    {copiedEvidenceId === citationKey
                      ? `✓ ${typedT.copiedEvidence || "Copied!"}`
                      : `📋 ${typedT.copyEvidence || "Copy Evidence"}`}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
