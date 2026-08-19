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
            const isConcise = Boolean(fullTextCitationMap[citationKey]);
            const displayText = isConcise && c.excerpt ? c.excerpt : (c.text || c.excerpt || "");

            return (
              <div
                key={idx}
                className="mono-card rounded-xl p-3 text-xs space-y-2 border border-accent-bright/20 bg-card/60"
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
                      <span className="font-mono text-[10px] text-ink-dim mono-inset px-2 py-0.5 rounded">
                        {typedT.relevanceScore || "Relevance"}: {Math.round(c.absolute_relevance * 100)}%
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
