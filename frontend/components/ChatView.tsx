"use client";

import { useState, useRef, useEffect } from "react";
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
  citations?: Array<{
    source_id: string;
    document_name: string;
    section_title: string;
    section_number: string;
    page_number: number;
    source_url: string;
  }>;
  latency_ms?: number;
  model?: string;
  cache_hit?: boolean;
  evidence_found?: boolean;
  query?: string;
  timestamp: string;
}

interface ChatViewProps {
  lang: Language;
  topK: number;
  onTopKChange: (k: number) => void;
}

export function ChatView({ lang, topK, onTopKChange }: ChatViewProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const t = translations[lang] || translations.en;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isGenerating]);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleClearChat = () => {
    setMessages([]);
    setError(null);
  };

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
      await generateStream(text, topK, {
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
      }, historyPayload);
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

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Top Consultation Bar */}
      <div className="mono-card flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4">
        <div className="flex items-center gap-3">
          <div className="mono-button flex h-9 w-9 items-center justify-center rounded-xl font-mono text-xs font-extrabold text-accent-bright border border-accent-bright/20 shadow-sm">
            AI
          </div>
          <div>
            <h2 className="text-sm font-extrabold text-ink">{t.chatTab || "💬 RAG Chatbot"}</h2>
            <p className="text-[11px] text-ink-dim flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-bright animate-pulse" />
              {t.groundedInNice || "Strictly Grounded in NICE NG243"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
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

          {messages.length > 0 && (
            <button
              type="button"
              onClick={handleClearChat}
              className="mono-button text-xs font-semibold px-3 py-1.5 rounded-xl text-ink-dim hover:text-ink transition-all cursor-pointer"
            >
              🔄 {t.newChatBtn || "New Consultation"}
            </button>
          )}
        </div>
      </div>

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
            {messages.map((msg) => (
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
                  className={`max-w-[85%] rounded-2xl p-4 sm:p-5 ${
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
                          cached
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

                  {/* Citations Block */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-4 border-t border-line/40 pt-3 space-y-2">
                      <div className="text-[11px] font-extrabold uppercase tracking-wider text-ink-faint">
                        {t.citationsLabel || "Evidence Sources:"}
                      </div>
                      <div className="grid grid-cols-1 gap-2">
                        {msg.citations.map((c, idx) => (
                          <div
                            key={idx}
                            className="mono-card flex items-start gap-2.5 rounded-xl p-2.5 text-xs text-ink-dim border border-line/40"
                          >
                            <span className="mono-pill px-1.5 py-0.5 font-mono text-[10px] font-extrabold text-accent-bright">
                              [{c.source_id}]
                            </span>
                            <div className="flex-1">
                              <p className="font-bold text-ink text-[12px]">{c.document_name}</p>
                              <p className="text-[11px] text-ink-faint mt-0.5">
                                {c.section_number ? `${c.section_number} ` : ""}
                                {c.section_title}
                                {c.page_number ? ` · Page ${c.page_number}` : ""}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Action Bar */}
                  {msg.role === "assistant" && msg.content && (
                    <div className="mt-3 flex items-center justify-end gap-2 pt-2 text-[11px]">
                      <button
                        type="button"
                        onClick={() => handleCopy(msg.id, msg.content)}
                        className="mono-button px-2.5 py-1 rounded-lg text-ink-faint hover:text-ink transition-all cursor-pointer"
                      >
                        {copiedId === msg.id ? `✓ ${t.copied || "Copied!"}` : `📋 ${t.copyAnswer || "Copy"}`}
                      </button>
                    </div>
                  )}
                </div>

                {msg.role === "user" && (
                  <div className="mono-card flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-xs font-bold text-ink-dim border border-line/60 mt-1">
                    👤
                  </div>
                )}
              </div>
            ))}
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
