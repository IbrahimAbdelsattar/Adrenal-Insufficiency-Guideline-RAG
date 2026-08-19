"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "@/lib/api";
import type { ChatMessage as ChatMessageType } from "@/components/ChatView";
import { HighlightMatches } from "@/components/HighlightMatches";
import { CitationMarkers } from "@/components/CitationMarkers";
import { EvidencePanel } from "./EvidencePanel";

interface ChatMessageProps {
  msg: ChatMessageType;
  t: Record<string, unknown>;
  isEvidenceExpanded: boolean;
  onToggleEvidence: () => void;
  copiedId: string | null;
  onCopy: (id: string, text: string) => void;
  copiedEvidenceId: string | null;
  onCopyEvidence: (id: string, text: string) => void;
  fullTextCitationMap: Record<string, boolean>;
  onToggleFullText: (citationKey: string) => void;
  onCite: (sourceId: string) => void;
  highlightedCitationKey: string | null;
  onAskClarifying: (question: string) => void;
}

/** Plain-text rendering of one citation for clipboard export. */
function citationToText(c: Citation): string {
  const loc = [
    c.section_number ? `§${c.section_number}` : "",
    c.section_title,
    c.page_number ? `p.${c.page_number}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return `[Source ${c.source_id}] ${c.document_name}${loc ? ` (${loc})` : ""}\n${
    c.excerpt || c.text || ""
  }`;
}

const GROUNDING_BADGE_STYLE: Record<string, string> = {
  verified: "text-accent-bright border-accent-bright/40",
  failed: "text-caution border-caution/40",
  abstained: "text-ink-faint border-line/50",
};

export function ChatMessage({
  msg,
  t,
  isEvidenceExpanded,
  onToggleEvidence,
  copiedId,
  onCopy,
  copiedEvidenceId,
  onCopyEvidence,
  fullTextCitationMap,
  onToggleFullText,
  onCite,
  highlightedCitationKey,
  onAskClarifying,
}: ChatMessageProps) {
  const typedT = t as Record<string, string>;
  const hasCitations = Boolean(msg.citations && msg.citations.length > 0);
  const hasClarifying = Boolean(msg.clarifying_questions && msg.clarifying_questions.length > 0);

  const groundingLabel =
    msg.grounding_status === "failed"
      ? typedT.groundingFailedBadge || "Unverified"
      : msg.grounding_status === "abstained"
        ? typedT.groundingAbstainedBadge || "No Answer"
        : typedT.groundingVerifiedBadge || "Verified";

  const buildAnswerWithCitations = () => {
    let out = msg.content;
    if (msg.citations && msg.citations.length > 0) {
      out += "\n\n---\nSources:\n" + msg.citations.map(citationToText).join("\n\n");
    }
    return out;
  };

  const buildAllEvidenceText = () =>
    (msg.citations || []).map(citationToText).join("\n\n---\n\n");

  return (
    <div
      className={`flex gap-3 ${
        msg.role === "user" ? "justify-end" : "justify-start"
      } animate-fade-in-up`}
    >
      {msg.role === "assistant" && (
        <div className="mono-card flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-xs font-bold text-accent-bright border border-accent-bright/20 shadow-sm mt-1">
          AI
        </div>
      )}

      <div
        className={`max-w-[88%] sm:max-w-[82%] rounded-2xl p-4 sm:p-5 ${
          msg.role === "user"
            ? "mono-button-primary text-white ml-auto"
            : "mono-inset text-ink"
        }`}
      >
        {/* Message Header */}
        <div className="flex items-center justify-between gap-3 text-[11px] mb-2 border-b border-line/30 pb-2">
          <span className="font-bold opacity-80">
            {msg.role === "user"
              ? typedT.clinicianRole || "Clinician"
              : typedT.assistantRole || "Eva AI (CDS)"}
          </span>
          <div className="flex items-center gap-2">
            {msg.role === "assistant" && msg.latency_ms ? (
              <span className="font-mono text-[10px] opacity-75">
                ⚡ {msg.latency_ms}ms
              </span>
            ) : null}
            {msg.cache_hit && (
              <span className="mono-pill px-1.5 py-0.2 text-[9px] font-extrabold uppercase text-accent-bright">
                {typedT.servedFromCache || "cached"}
              </span>
            )}
            {msg.role === "assistant" && msg.content && msg.grounding_status && (
              <span
                className={`mono-pill px-1.5 py-0.2 text-[9px] font-extrabold uppercase ${
                  GROUNDING_BADGE_STYLE[msg.grounding_status] || GROUNDING_BADGE_STYLE.verified
                }`}
                title={
                  msg.grounding_status === "verified"
                    ? "Every clinical claim resolved to a cited passage"
                    : msg.grounding_status === "failed"
                      ? "Grounding could not be verified; answer withheld"
                      : "No answer was generated"
                }
              >
                {groundingLabel}
              </span>
            )}
            <span className="opacity-60 text-[10px]">{msg.timestamp}</span>
          </div>
        </div>

        {/* Message Body */}
        <div className="text-sm leading-relaxed">
          {msg.content ? (
            msg.role === "assistant" ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({ children }) => (
                    <h3 className="mb-3 mt-5 text-lg font-bold first:mt-0">
                      <HighlightMatches query={msg.query || ""}>{children}</HighlightMatches>
                    </h3>
                  ),
                  h2: ({ children }) => (
                    <h4 className="mb-3 mt-4 text-base font-bold first:mt-0">
                      <HighlightMatches query={msg.query || ""}>{children}</HighlightMatches>
                    </h4>
                  ),
                  h3: ({ children }) => (
                    <h5 className="mb-2 mt-3 text-sm font-bold first:mt-0">
                      <HighlightMatches query={msg.query || ""}>{children}</HighlightMatches>
                    </h5>
                  ),
                  p: ({ children }) => (
                    <p className="mb-3 last:mb-0">
                      <HighlightMatches query={msg.query || ""}>{children}</HighlightMatches>
                    </p>
                  ),
                  ul: ({ children }) => (
                    <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
                  ),
                  li: ({ children }) => <li className="pl-1">{children}</li>,
                  blockquote: ({ children }) => (
                    <blockquote className="mb-3 border-l-2 border-accent-bright/60 pl-3 text-ink-dim">
                      <HighlightMatches query={msg.query || ""}>{children}</HighlightMatches>
                    </blockquote>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-bold text-ink">{children}</strong>
                  ),
                  code: ({ children }) => (
                    <code className="break-words rounded bg-ink/10 px-1 py-0.5 font-mono text-[0.9em]">
                      {children}
                    </code>
                  ),
                  pre: ({ children }) => (
                    <pre className="mb-3 overflow-x-auto rounded-xl bg-ink/10 p-3 font-mono text-xs">
                      {children}
                    </pre>
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
                      <table className="min-w-full border-collapse text-left text-xs">
                        {children}
                      </table>
                    </div>
                  ),
                  th: ({ children }) => (
                    <th className="border-b border-line/60 bg-ink/5 px-2 py-1.5 font-bold">
                      <HighlightMatches query={msg.query || ""}>{children}</HighlightMatches>
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="border-b border-line/40 px-2 py-1.5 align-top">
                      <HighlightMatches query={msg.query || ""}>{children}</HighlightMatches>
                    </td>
                  ),
                  hr: () => <hr className="my-3 border-line/60" />,
                }}
              >
                {msg.content}
              </ReactMarkdown>
            ) : (
              <span className="whitespace-pre-wrap">{msg.content}</span>
            )
          ) : (
            <div className="flex items-center gap-2 text-ink-dim py-2">
              <span className="h-2 w-2 rounded-full bg-accent-bright animate-pulse" />
              <span className="text-xs">
                {typedT.generatingBtn || "Synthesizing clinical response from NICE NG243..."}
              </span>
            </div>
          )}
        </div>

        {/* Evidence Panel */}
        {msg.role === "assistant" && hasCitations && (
          <EvidencePanel
            citations={msg.citations || []}
            query={msg.query || ""}
            isExpanded={isEvidenceExpanded}
            onToggleExpand={onToggleEvidence}
            copiedEvidenceId={copiedEvidenceId}
            onCopyEvidence={onCopyEvidence}
            fullTextCitationMap={fullTextCitationMap}
            onToggleFullText={onToggleFullText}
            t={typedT}
            msgId={msg.id}
          />
        )}

        {/* Action Bar */}
        {msg.role === "assistant" && msg.content && (
          <div className="mt-3 flex items-center justify-between border-t border-line/30 pt-2 text-[11px]">
            <span className="text-[10px] text-ink-faint font-mono">
              {msg.model || "eva-ai"}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onCopy(msg.id, msg.content)}
                className="mono-button px-2.5 py-1 rounded-lg text-ink-faint hover:text-ink transition-all cursor-pointer font-semibold"
              >
                {copiedId === msg.id
                  ? `✓ ${typedT.copied || "Copied!"}`
                  : `📋 ${typedT.copyAnswer || "Copy"}`}
              </button>
            </div>
          </div>
        )}
      </div>

      {msg.role === "user" && (
        <div className="mono-card flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-xs font-bold text-ink-dim border border-line/60 mt-1">
          👤
        </div>
      )}
    </div>
  );
}
