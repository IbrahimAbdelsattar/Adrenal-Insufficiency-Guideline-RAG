"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Language } from "@/lib/translations";
import { translations } from "@/lib/translations";
import { generateStream, generate } from "@/lib/api";
import type { Citation } from "@/lib/api";
import { HighlightMatches } from "@/components/HighlightMatches";

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

const SESSIONS_STORAGE_KEY = "eva_ai_consultation_sessions_v1";
const ACTIVE_SESSION_STORAGE_KEY = "eva_ai_active_session_id_v1";

export function ChatView({ lang, topK, onTopKChange }: ChatViewProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [inputQuery, setInputQuery] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copiedEvidenceId, setCopiedEvidenceId] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [expandedEvidenceMsgId, setExpandedEvidenceMsgId] = useState<string | null>(null);
  const [fullTextCitationMap, setFullTextCitationMap] = useState<Record<string, boolean>>({});

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const t = translations[lang] || translations.en;

  // ---------------------------------------------------------------------------
  // Load & Persist Sessions from LocalStorage
  // ---------------------------------------------------------------------------
  useEffect(() => {
    try {
      const savedSessions = localStorage.getItem(SESSIONS_STORAGE_KEY);
      const savedActiveId = localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);

      if (savedSessions) {
        const parsed: ChatSession[] = JSON.parse(savedSessions);
        if (parsed.length > 0) {
          setSessions(parsed);
          const active = parsed.find((s) => s.id === savedActiveId) || parsed[0];
          setActiveSessionId(active.id);
          return;
        }
      }

      // Initialize default session if none exists
      const initialId = `session-${Date.now()}`;
      const newSession: ChatSession = {
        id: initialId,
        title: t.untitledSession || "New Clinical Inquiry",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: [],
        topK,
      };
      setSessions([newSession]);
      setActiveSessionId(initialId);
    } catch {
      // Fallback in case localStorage is disabled or corrupted
      const initialId = `session-${Date.now()}`;
      setSessions([
        {
          id: initialId,
          title: t.untitledSession || "New Clinical Inquiry",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messages: [],
          topK,
        },
      ]);
      setActiveSessionId(initialId);
    }
  }, []);

  // Save sessions to localStorage on change
  useEffect(() => {
    if (sessions.length > 0) {
      try {
        localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(sessions));
      } catch {
        // Ignore quota errors
      }
    }
  }, [sessions]);

  // Save active session ID to localStorage
  useEffect(() => {
    if (activeSessionId) {
      try {
        localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeSessionId);
      } catch {
        // Ignore
      }
    }
  }, [activeSessionId]);

  // Active Session & Messages
  const currentSession = useMemo(() => {
    return sessions.find((s) => s.id === activeSessionId) || sessions[0];
  }, [sessions, activeSessionId]);

  const messages = useMemo(() => {
    return currentSession?.messages || [];
  }, [currentSession]);

  const setMessages = (
    updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
  ) => {
    setSessions((prevSessions) =>
      prevSessions.map((session) => {
        if (session.id === activeSessionId) {
          const nextMessages =
            typeof updater === "function" ? updater(session.messages) : updater;
          // Auto-generate title from first user query if still untitled
          let nextTitle = session.title;
          if (
            (!nextTitle || nextTitle === t.untitledSession || nextTitle === "New Clinical Inquiry") &&
            nextMessages.length > 0
          ) {
            const firstUserMsg = nextMessages.find((m) => m.role === "user");
            if (firstUserMsg) {
              nextTitle =
                firstUserMsg.content.slice(0, 48) +
                (firstUserMsg.content.length > 48 ? "..." : "");
            }
          }
          return {
            ...session,
            title: nextTitle,
            updatedAt: new Date().toISOString(),
            messages: nextMessages,
          };
        }
        return session;
      }),
    );
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isGenerating]);

  // ---------------------------------------------------------------------------
  // Session Actions
  // ---------------------------------------------------------------------------
  const handleNewSession = () => {
    const newId = `session-${Date.now()}`;
    const newSession: ChatSession = {
      id: newId,
      title: t.untitledSession || "New Clinical Inquiry",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [],
      topK,
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newId);
    setIsHistoryOpen(false);
    setError(null);
    setInputQuery("");
  };

  const handleDeleteSession = (sessionIdToDelete: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setSessions((prev) => {
      const filtered = prev.filter((s) => s.id !== sessionIdToDelete);
      if (filtered.length === 0) {
        const fallbackId = `session-${Date.now()}`;
        const fresh: ChatSession = {
          id: fallbackId,
          title: t.untitledSession || "New Clinical Inquiry",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messages: [],
          topK,
        };
        setActiveSessionId(fallbackId);
        return [fresh];
      }
      if (activeSessionId === sessionIdToDelete) {
        setActiveSessionId(filtered[0].id);
      }
      return filtered;
    });
  };

  const handleClearAllHistory = () => {
    if (window.confirm("Are you sure you want to clear all consultation history?")) {
      const freshId = `session-${Date.now()}`;
      const freshSession: ChatSession = {
        id: freshId,
        title: t.untitledSession || "New Clinical Inquiry",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: [],
        topK,
      };
      setSessions([freshSession]);
      setActiveSessionId(freshId);
      setIsHistoryOpen(false);
    }
  };

  const handleExportSession = (sessionToExport: ChatSession, e?: React.MouseEvent) => {
    e?.stopPropagation();
    let exportText = `# Eva AI Clinical Consultation Summary\n`;
    exportText += `**Session Title:** ${sessionToExport.title}\n`;
    exportText += `**Date:** ${new Date(sessionToExport.createdAt).toLocaleString()}\n`;
    exportText += `**Guideline Scope:** NICE NG243 (Adrenal Insufficiency Management)\n\n---\n\n`;

    sessionToExport.messages.forEach((m, idx) => {
      exportText += `### [${m.role === "user" ? "Clinician Query" : "Eva AI Decision Support"}] - ${m.timestamp}\n\n`;
      exportText += `${m.content}\n\n`;
      if (m.citations && m.citations.length > 0) {
        exportText += `#### Evidence Sources:\n`;
        m.citations.forEach((c) => {
          exportText += `- **[Source ${c.source_id}] ${c.document_name}** | Section ${c.section_number} (${c.section_title}) | Page ${c.page_number}\n`;
          if (c.excerpt) {
            exportText += `  > ${c.excerpt}\n`;
          }
        });
        exportText += `\n`;
      }
      if (idx < sessionToExport.messages.length - 1) {
        exportText += `---\n\n`;
      }
    });

    const blob = new Blob([exportText], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `eva-ai-consultation-${sessionToExport.id}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

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

  // ---------------------------------------------------------------------------
  // Send Message & Stream Response
  // ---------------------------------------------------------------------------
  const handleSend = async (queryToSend?: string) => {
    const text = (queryToSend || inputQuery).trim();
    if (!text || isGenerating) return;

    setInputQuery("");
    setError(null);

    const userMessageId = `user-${Date.now()}`;
    const assistantMessageId = `assistant-${Date.now()}`;
    const currentTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    const userMsg: ChatMessage = {
      id: userMessageId,
      role: "user",
      content: text,
      timestamp: currentTime,
    };

    const initialAssistantMsg: ChatMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      citations: [],
      latency_ms: 0,
      query: text,
      timestamp: currentTime,
    };

    setMessages((prev) => [...prev, userMsg, initialAssistantMsg]);
    setIsGenerating(true);

    let accumulatedText = "";
    let streamFailed = false;

    // Convert prior conversation history for backend context
    const historyPayload = messages
      .filter((m) => m.content.trim())
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      await generateStream(
        text,
        topK,
        {
          onMeta: (meta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      model: meta.model,
                      evidence_found: meta.evidence_found,
                      cache_hit: meta.cache_hit,
                    }
                  : m,
              ),
            );
          },
          onToken: (delta) => {
            accumulatedText += delta;
            const currentSnapshot = accumulatedText;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? { ...m, content: currentSnapshot }
                  : m,
              ),
            );
          },
          onDone: (done) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      citations: done.citations,
                      latency_ms: done.latency_ms,
                    }
                  : m,
              ),
            );
          },
          onError: (errDetail) => {
            streamFailed = true;
            setError(errDetail);
          },
        },
        historyPayload,
      );
    } catch {
      streamFailed = true;
    }

    // Fallback to standard generate POST if streaming experienced a network error and yielded no text
    if (streamFailed && !accumulatedText) {
      try {
        setError(null);
        const fallbackRes = await generate(text, topK, historyPayload);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  content: fallbackRes.answer,
                  citations: fallbackRes.citations,
                  latency_ms: fallbackRes.latency_ms,
                  model: fallbackRes.model,
                  cache_hit: fallbackRes.cache_hit,
                  evidence_found: fallbackRes.evidence_found,
                }
              : m,
          ),
        );
      } catch (fallbackErr) {
        const errorMsg =
          fallbackErr instanceof Error ? fallbackErr.message : "Generation failed.";
        setError(errorMsg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  content: "⚠️ " + errorMsg,
                }
              : m,
          ),
        );
      }
    }

    setIsGenerating(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Filtered Sessions for Search
  const filteredSessions = useMemo(() => {
    if (!historySearch.trim()) return sessions;
    const query = historySearch.toLowerCase();
    return sessions.filter(
      (s) =>
        s.title.toLowerCase().includes(query) ||
        s.messages.some((m) => m.content.toLowerCase().includes(query)),
    );
  }, [sessions, historySearch]);

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
              <span className="text-[11px] font-bold text-ink-dim max-w-[200px] truncate hidden sm:inline">
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
          {/* History Drawer Toggle Button */}
          <button
            type="button"
            onClick={() => setIsHistoryOpen((prev) => !prev)}
            className={`mono-button flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              isHistoryOpen ? "bg-accent-bright/15 text-accent-bright border-accent-bright/40" : "text-ink-dim hover:text-ink"
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
            onClick={handleNewSession}
            className="mono-button-primary flex items-center gap-1 text-xs font-bold px-3 py-1.5 rounded-xl text-white shadow-sm hover:scale-[1.02] transition-all cursor-pointer"
          >
            <span>➕</span>
            <span className="hidden sm:inline">{t.newChatBtn || "New Consultation"}</span>
          </button>
        </div>
      </div>

      {/* History Slide-Out Drawer / Modal */}
      {isHistoryOpen && (
        <div className="mono-card rounded-2xl p-4 border border-accent-bright/30 bg-card/95 shadow-xl animate-fade-in-up space-y-4">
          <div className="flex items-center justify-between border-b border-line/40 pb-3">
            <div className="flex items-center gap-2">
              <span className="text-base">📜</span>
              <h3 className="text-sm font-extrabold text-ink">
                {t.consultationHistory || "Consultation History"}
              </h3>
              <span className="text-xs text-ink-faint">
                ({sessions.length} {t.historySessionsCount || "sessions"})
              </span>
            </div>
            <div className="flex items-center gap-2">
              {sessions.length > 1 && (
                <button
                  type="button"
                  onClick={handleClearAllHistory}
                  className="text-[11px] text-caution hover:underline cursor-pointer"
                >
                  {t.clearAllHistory || "Clear All"}
                </button>
              )}
              <button
                type="button"
                onClick={() => setIsHistoryOpen(false)}
                className="mono-button h-6 w-6 flex items-center justify-center rounded-lg text-ink-dim hover:text-ink text-xs font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Search History */}
          <div className="relative">
            <input
              type="text"
              value={historySearch}
              onChange={(e) => setHistorySearch(e.target.value)}
              placeholder={t.searchHistoryPlaceholder || "Search previous consultations..."}
              className="w-full rounded-xl bg-transparent px-3 py-1.5 text-xs text-ink placeholder:text-ink-faint focus:outline-none mono-inset"
            />
          </div>

          {/* Session Cards List */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 max-h-[260px] overflow-y-auto pr-1">
            {filteredSessions.length === 0 ? (
              <div className="col-span-full py-6 text-center text-xs text-ink-dim">
                {t.noHistoryFound || "No previous consultations found"}
              </div>
            ) : (
              filteredSessions.map((session) => {
                const isActive = session.id === activeSessionId;
                const messageCount = session.messages.length;
                return (
                  <div
                    key={session.id}
                    onClick={() => {
                      setActiveSessionId(session.id);
                      setIsHistoryOpen(false);
                    }}
                    className={`mono-card-interactive p-3 rounded-xl flex flex-col justify-between gap-2 text-left cursor-pointer transition-all ${
                      isActive
                        ? "border-accent-bright/60 bg-accent-bright/10 shadow-sm"
                        : "border-line/40 hover:border-line"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-1.5">
                      <h4 className="text-xs font-bold text-ink line-clamp-2 leading-snug">
                        {session.title || t.untitledSession}
                      </h4>
                      {isActive && (
                        <span className="mono-pill px-1.5 py-0.2 text-[9px] font-extrabold text-accent-bright shrink-0">
                          {t.activeSession || "Active"}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-ink-faint border-t border-line/30 pt-1.5 mt-1">
                      <span>{new Date(session.updatedAt || session.createdAt).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                      <div className="flex items-center gap-1.5">
                        <span>💬 {messageCount}</span>
                        <button
                          type="button"
                          title={t.exportSession || "Export Summary"}
                          onClick={(e) => handleExportSession(session, e)}
                          className="hover:text-accent-bright p-0.5 rounded transition-colors"
                        >
                          📥
                        </button>
                        <button
                          type="button"
                          title={t.deleteSession || "Delete"}
                          onClick={(e) => handleDeleteSession(session.id, e)}
                          className="hover:text-caution p-0.5 rounded transition-colors"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Error Notification */}
      {error && (
        <div className="mono-card rounded-2xl border-caution/40 bg-caution/5 p-4 text-caution text-xs flex items-center gap-2 animate-fade-in-up">
          <span>⚠️ {error}</span>
        </div>
      )}

      {/* Chat Messages Container */}
      <div className="mono-card rounded-2xl p-4 sm:p-6 min-h-[420px] max-h-[620px] overflow-y-auto space-y-6">
        {messages.length === 0 ? (
          /* Empty Consultation State */
          <div className="py-8 text-center space-y-6 animate-fade-in-up">
            <div className="mono-button mx-auto flex h-16 w-16 items-center justify-center rounded-2xl text-accent-bright border border-accent-bright/20 shadow-md">
              <span className="font-brand-cursive text-3xl text-accent-bright">E</span>
              <span className="font-brand-serif text-sm font-bold text-accent-bright -ml-0.5">A</span>
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
                {t.exemplars.map((ex, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => handleSend(ex.query)}
                    className="mono-card-interactive text-left p-3 rounded-xl transition-all cursor-pointer group"
                  >
                    <div className="flex items-center justify-between text-[11px] text-ink-faint mb-1">
                      <span className="font-bold text-accent-bright">{ex.category}</span>
                      <span className="opacity-0 group-hover:opacity-100 transition-opacity">↵</span>
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
          /* Conversation Message List */
          <div className="space-y-6">
            {messages.map((msg) => {
              const isEvidenceExpanded = expandedEvidenceMsgId === msg.id;
              const hasCitations = Boolean(msg.citations && msg.citations.length > 0);

              return (
                <div
                  key={msg.id}
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
                          ? t.clinicianRole || "Clinician"
                          : t.assistantRole || "Eva AI (CDS)"}
                      </span>
                      <div className="flex items-center gap-2">
                        {msg.role === "assistant" && msg.latency_ms ? (
                          <span className="font-mono text-[10px] opacity-75">
                            ⚡ {msg.latency_ms}ms
                          </span>
                        ) : null}
                        {msg.cache_hit && (
                          <span className="mono-pill px-1.5 py-0.2 text-[9px] font-extrabold uppercase text-accent-bright">
                            {t.servedFromCache || "cached"}
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
                              h1: ({ children }) => <h3 className="mb-3 mt-5 text-lg font-bold first:mt-0"><HighlightMatches query={msg.query || ""}>{children}</HighlightMatches></h3>,
                              h2: ({ children }) => <h4 className="mb-3 mt-4 text-base font-bold first:mt-0"><HighlightMatches query={msg.query || ""}>{children}</HighlightMatches></h4>,
                              h3: ({ children }) => <h5 className="mb-2 mt-3 text-sm font-bold first:mt-0"><HighlightMatches query={msg.query || ""}>{children}</HighlightMatches></h5>,
                              p: ({ children }) => <p className="mb-3 last:mb-0"><HighlightMatches query={msg.query || ""}>{children}</HighlightMatches></p>,
                              ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
                              ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
                              li: ({ children }) => <li className="pl-1">{children}</li>,
                              blockquote: ({ children }) => <blockquote className="mb-3 border-l-2 border-accent-bright/60 pl-3 text-ink-dim"><HighlightMatches query={msg.query || ""}>{children}</HighlightMatches></blockquote>,
                              strong: ({ children }) => <strong className="font-bold text-ink">{children}</strong>,
                              code: ({ children }) => <code className="break-words rounded bg-ink/10 px-1 py-0.5 font-mono text-[0.9em]">{children}</code>,
                              pre: ({ children }) => <pre className="mb-3 overflow-x-auto rounded-xl bg-ink/10 p-3 font-mono text-xs">{children}</pre>,
                              a: ({ children, href }) => <a className="break-words text-accent-bright underline underline-offset-2" href={href} rel="noreferrer" target="_blank">{children}</a>,
                              table: ({ children }) => <div className="mb-3 overflow-x-auto rounded-xl border border-line/60"><table className="min-w-full border-collapse text-left text-xs">{children}</table></div>,
                              th: ({ children }) => <th className="border-b border-line/60 bg-ink/5 px-2 py-1.5 font-bold"><HighlightMatches query={msg.query || ""}>{children}</HighlightMatches></th>,
                              td: ({ children }) => <td className="border-b border-line/40 px-2 py-1.5 align-top"><HighlightMatches query={msg.query || ""}>{children}</HighlightMatches></td>,
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
                            {t.generatingBtn || "Synthesizing clinical response from NICE NG243..."}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Historical Citations & Evidence Inspector Block */}
                    {hasCitations && (
                      <div className="mt-4 border-t border-line/40 pt-3 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <div className="text-[11px] font-extrabold uppercase tracking-wider text-ink-faint flex items-center gap-1.5">
                            <span>{t.citationsLabel || "Evidence Sources:"}</span>
                            <span className="mono-pill px-1.5 py-0.2 text-[9px] font-mono font-extrabold text-accent-bright">
                              {msg.citations?.length}
                            </span>
                          </div>

                          {/* Toggle Evidence Drawer Button */}
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedEvidenceMsgId((prev) => (prev === msg.id ? null : msg.id))
                            }
                            className="mono-button flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold text-accent-bright hover:text-accent-bright/80 transition-all cursor-pointer"
                          >
                            <span>{isEvidenceExpanded ? "▲" : "▼"}</span>
                            <span>
                              {isEvidenceExpanded
                                ? t.hideEvidence || "Hide Evidence"
                                : t.viewEvidence || "View Retrieved Evidence"}
                            </span>
                          </button>
                        </div>

                        {/* Collapsed Citations Quick Chips */}
                        {!isEvidenceExpanded && (
                          <div className="flex flex-wrap gap-1.5 pt-1">
                            {msg.citations?.map((c, idx) => (
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

                        {/* Expanded Full Evidence Chunks Inspector */}
                        {isEvidenceExpanded && (
                          <div className="space-y-3 pt-2 animate-fade-in-up">
                            {msg.citations?.map((c, idx) => {
                              const citationKey = `${msg.id}-${c.source_id}-${idx}`;
                              const isFullText = Boolean(fullTextCitationMap[citationKey]);
                              const displayText = isFullText && c.text ? c.text : (c.excerpt || c.text || "");

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
                                          {t.relevanceScore || "Relevance"}: {Math.round(c.absolute_relevance * 100)}%
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

                                  {/* Evidence Text Excerpt */}
                                  <div className="text-[12px] leading-relaxed text-ink-dim bg-ink/5 p-2.5 rounded-lg border border-line/30 font-sans">
                                    <HighlightMatches query={msg.query || ""}>
                                      {displayText}
                                    </HighlightMatches>
                                  </div>

                                  {/* Evidence Action Controls */}
                                  <div className="flex items-center justify-between pt-1 text-[11px]">
                                    {c.text && c.text.length > (c.excerpt?.length || 0) ? (
                                      <button
                                        type="button"
                                        onClick={() => toggleFullText(citationKey)}
                                        className="text-accent-bright hover:underline font-semibold cursor-pointer"
                                      >
                                        {isFullText
                                          ? `▲ ${t.conciseExcerpt || "Show Concise Excerpt"}`
                                          : `▼ ${t.fullGuidelineText || "Show Full Guideline Chunk Text"}`}
                                      </button>
                                    ) : <div />}

                                    <button
                                      type="button"
                                      onClick={() => handleCopyEvidence(citationKey, displayText)}
                                      className="mono-button px-2 py-0.5 rounded text-[10px] text-ink-dim hover:text-ink transition-all cursor-pointer"
                                    >
                                      {copiedEvidenceId === citationKey
                                        ? `✓ ${t.copiedEvidence || "Copied!"}`
                                        : `📋 ${t.copyEvidence || "Copy Evidence"}`}
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
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
                            onClick={() => handleCopy(msg.id, msg.content)}
                            className="mono-button px-2.5 py-1 rounded-lg text-ink-faint hover:text-ink transition-all cursor-pointer font-semibold"
                          >
                            {copiedId === msg.id ? `✓ ${t.copied || "Copied!"}` : `📋 ${t.copyAnswer || "Copy"}`}
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
            })}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="mono-card rounded-2xl p-3 sm:p-4 space-y-3">
        <div className="relative">
          <textarea
            ref={textareaRef}
            rows={2}
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isGenerating}
            placeholder={t.chatPlaceholder || "Ask Eva AI a clinical question based on NICE NG243..."}
            className="w-full resize-none rounded-xl bg-transparent px-3.5 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none mono-inset"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="text-[11px] text-ink-faint hidden sm:inline">
            {t.shortcutSend || "Press Enter ↵ to send, Shift+Enter for new line"}
          </span>

          <div className="flex items-center gap-2 ml-auto">
            <button
              type="button"
              onClick={() => handleSend()}
              disabled={!inputQuery.trim() || isGenerating}
              className={`mono-button-primary flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-extrabold text-white transition-all cursor-pointer ${
                !inputQuery.trim() || isGenerating ? "opacity-50 cursor-not-allowed" : "shadow-md hover:scale-[1.02]"
              }`}
            >
              {isGenerating ? (
                <>
                  <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
                  <span>{t.generatingBtn || "Generating..."}</span>
                </>
              ) : (
                <>
                  <span>{t.sendBtn || "Send"}</span>
                  <span>↵</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
