"use client";

import { useState, useRef, useEffect } from "react";
import type { Language } from "@/lib/translations";
import { translations } from "@/lib/translations";
import type { Citation, GroundingStatus, InputRiskAssessment } from "@/lib/api";
import { useChatSessions } from "@/hooks/useChatSessions";
import { useStreamingChat } from "@/hooks/useStreamingChat";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { ChatHistory } from "@/components/chat/ChatHistory";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  latency_ms?: number;
  model?: string;
  cache_hit?: boolean;
  evidence_found?: boolean;
  query?: string;
  timestamp: string;
  grounding_status?: GroundingStatus;
  clarifying_questions?: string[];
  risk_assessment?: InputRiskAssessment;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
  topK: number;
}

interface ChatViewProps {
  lang: Language;
  topK: number;
  onTopKChange: (k: number) => void;
}

export function ChatView({ lang, topK, onTopKChange }: ChatViewProps) {
  const [inputQuery, setInputQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copiedEvidenceId, setCopiedEvidenceId] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [expandedEvidenceMsgId, setExpandedEvidenceMsgId] = useState<string | null>(null);
  const [fullTextCitationMap, setFullTextCitationMap] = useState<Record<string, boolean>>({});
  const [highlightedCitationKey, setHighlightedCitationKey] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const t = translations[lang] || translations.en;

  // Hooks
  const {
    sessions,
    activeSessionId,
    currentSession,
    messages,
    setMessages,
    setActiveSessionId,
    handleNewSession,
    handleDeleteSession,
    handleClearAllHistory,
  } = useChatSessions(topK);

  const { isGenerating, error, handleSend: sendChat, clearError } = useStreamingChat();

  // Scroll to bottom on new messages, but only if the user is already near
  // the bottom — otherwise streaming tokens would repeatedly yank them back
  // down while they're reading earlier text.
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const nearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < 120;
    if (nearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, isGenerating]);

  // Copy helpers
  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleCopyEvidence = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedEvidenceId(id);
    setTimeout(() => setCopiedEvidenceId(null), 2000);
  };

  const toggleFullText = (citationId: string) => {
    setFullTextCitationMap((prev) => ({
      ...prev,
      [citationId]: !prev[citationId],
    }));
  };

  // Clicking a [Source N] marker inside an answer opens the evidence panel
  // (if collapsed) and scrolls to + flashes the matching citation card.
  const handleCiteClick = (msgId: string, sourceId: string) => {
    const key = `${msgId}-${sourceId}`;
    setExpandedEvidenceMsgId(msgId);
    setHighlightedCitationKey(key);
    requestAnimationFrame(() => {
      setTimeout(() => {
        document
          .querySelector(`[data-citation-anchor="${key}"]`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 60);
    });
    setTimeout(() => {
      setHighlightedCitationKey((prev) => (prev === key ? null : prev));
    }, 2200);
  };

  // Send wrapper
  const handleSend = async (queryToSend?: string) => {
    const text = (queryToSend || inputQuery).trim();
    if (!text || isGenerating) return;
    setInputQuery("");
    await sendChat(text, topK, messages, setMessages);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewSessionWithCleanup = () => {
    handleNewSession();
    setIsHistoryOpen(false);
    clearError();
    setInputQuery("");
  };

  return (
    <div className="flex flex-col h-full space-y-4 relative">
      {/* Top Consultation Navigation & Action Bar */}
      <div className="mono-card flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4">
        <div className="flex items-center gap-3">
          <div className="mono-button flex h-9 w-9 items-center justify-center rounded-xl font-mono text-xs font-extrabold text-accent-bright border border-accent-bright/20 shadow-sm">
            AI
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-extrabold text-ink">{t.chatTab || "💬 RAG Chatbot"}</h2>
              <span
                className="text-[11px] font-bold text-ink-dim max-w-[200px] truncate hidden sm:inline"
                suppressHydrationWarning
              >
                · {currentSession?.title || t.untitledSession}
              </span>
            </div>
            <p className="text-[11px] text-ink-dim flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-bright animate-pulse" />
              {t.groundedInNice || "Strictly Grounded in NICE NG243"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* History Toggle */}
          <button
            type="button"
            onClick={() => setIsHistoryOpen((prev) => !prev)}
            className={`mono-button flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              isHistoryOpen
                ? "bg-accent-bright/15 text-accent-bright border-accent-bright/40"
                : "text-ink-dim hover:text-ink"
            }`}
          >
            <span>📜</span>
            <span>{t.consultationHistory || "History"}</span>
            <span className="mono-pill px-1.5 py-0.2 text-[10px] font-mono font-extrabold text-accent-bright">
              {sessions.length}
            </span>
          </button>

          {/* Top-K selector */}
          <div className="flex items-center gap-1.5 text-xs text-ink-dim mono-inset px-2.5 py-1 rounded-xl">
            <span className="font-mono text-[11px] font-bold text-ink-faint">TOP-K:</span>
            {[3, 5, 8].map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => onTopKChange(k)}
                className={`px-2 py-0.5 rounded text-[11px] font-bold transition-all cursor-pointer ${
                  topK === k
                    ? "bg-accent-bright text-white shadow-sm"
                    : "text-ink-faint hover:text-ink"
                }`}
              >
                {k}
              </button>
            ))}
          </div>

          {/* New Chat Button */}
          <button
            type="button"
            onClick={handleNewSessionWithCleanup}
            className="mono-button-primary flex items-center gap-1 text-xs font-bold px-3 py-1.5 rounded-xl text-white shadow-sm hover:scale-[1.02] transition-all cursor-pointer"
          >
            <span>➕</span>
            <span className="hidden sm:inline">{t.newChatBtn || "New Consultation"}</span>
          </button>
        </div>
      </div>

      {/* History Drawer */}
      {isHistoryOpen && (
        <ChatHistory
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={setActiveSessionId}
          onDeleteSession={handleDeleteSession}
          onClearAll={handleClearAllHistory}
          onClose={() => setIsHistoryOpen(false)}
          t={t}
        />
      )}

      {/* Error */}
      {error && (
        <div className="mono-card rounded-2xl border-caution/40 bg-caution/5 p-4 text-caution text-xs flex items-center gap-2 animate-fade-in-up">
          <span>⚠️ {error}</span>
        </div>
      )}

      {/* Messages */}
      <div
        ref={messagesContainerRef}
        className="mono-card rounded-2xl p-4 sm:p-6 min-h-[420px] max-h-[620px] overflow-y-auto space-y-6"
      >
        {messages.length === 0 ? (
          /* Empty State */
          <div className="py-8 text-center space-y-6 animate-fade-in-up">
            <div className="mono-card mx-auto flex h-16 w-16 items-center justify-center rounded-2xl overflow-hidden border border-accent-bright/20 shadow-md">
              <img src="/icon.jpg" alt="Eva AI" className="h-full w-full object-cover rounded-2xl" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-ink">
                {t.chatWelcomeTitle || "Clinical RAG Chatbot"}
              </h3>
              <p className="mt-1.5 max-w-lg mx-auto text-xs leading-relaxed text-ink-dim">
                {t.chatWelcomeSubtitle ||
                  "Ask questions regarding adrenal insufficiency management. Answers are synthesized exclusively from NICE Guideline NG243 evidence blocks with verifiable structural citations."}
              </p>
            </div>

            {/* Quick Exemplar Prompts */}
            <div className="text-left max-w-xl mx-auto space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">
                {t.quickExemplars || "Quick Clinical Prompts:"}
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {t.exemplars.map((ex: { category: string; query: string }, i: number) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => handleSend(ex.query)}
                    className="mono-card-interactive text-left p-3 rounded-xl transition-all cursor-pointer group"
                  >
                    <div className="flex items-center justify-between text-[11px] text-ink-faint mb-1">
                      <span className="font-bold text-accent-bright">{ex.category}</span>
                      <span className="opacity-0 group-hover:opacity-100 transition-opacity">
                        ↵
                      </span>
                    </div>
                    <p className="text-xs font-semibold text-ink group-hover:text-accent-bright transition-colors">
                      {ex.query}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* Message List */
          <div className="space-y-6">
            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                msg={msg}
                t={t}
                isEvidenceExpanded={expandedEvidenceMsgId === msg.id}
                onToggleEvidence={() =>
                  setExpandedEvidenceMsgId((prev) => (prev === msg.id ? null : msg.id))
                }
                copiedId={copiedId}
                onCopy={handleCopy}
                copiedEvidenceId={copiedEvidenceId}
                onCopyEvidence={handleCopyEvidence}
                fullTextCitationMap={fullTextCitationMap}
                onToggleFullText={toggleFullText}
                onCite={(sourceId) => handleCiteClick(msg.id, sourceId)}
                highlightedCitationKey={highlightedCitationKey}
                onAskClarifying={handleSend}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <ChatComposer
        inputQuery={inputQuery}
        onInputChange={setInputQuery}
        onSend={() => handleSend()}
        onKeyDown={handleKeyDown}
        isGenerating={isGenerating}
        t={t}
      />
    </div>
  );
}
