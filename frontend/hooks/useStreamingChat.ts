import { useState, useCallback, useRef } from "react";
import { generateStream, generate } from "@/lib/api";
import type { ChatMessage } from "@/components/ChatView";

export interface UseStreamingChatReturn {
  isGenerating: boolean;
  error: string | null;
  handleSend: (
    query: string,
    topK: number,
    messages: ChatMessage[],
    setMessages: (
      updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
    ) => void,
  ) => Promise<void>;
  clearError: () => void;
}

export function useStreamingChat(): UseStreamingChatReturn {
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const handleSend = useCallback(
    async (
      query: string,
      topK: number,
      messages: ChatMessage[],
      setMessages: (
        updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
      ) => void,
    ) => {
      if (!query.trim() || isGenerating) return;

      setError(null);

      const userMessageId = `user-${Date.now()}`;
      const assistantMessageId = `assistant-${Date.now()}`;
      const currentTime = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });

      const userMsg: ChatMessage = {
        id: userMessageId,
        role: "user",
        content: query,
        timestamp: currentTime,
      };

      const initialAssistantMsg: ChatMessage = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        citations: [],
        latency_ms: 0,
        query,
        timestamp: currentTime,
      };

      setMessages((prev) => [...prev, userMsg, initialAssistantMsg]);
      setIsGenerating(true);

      let accumulatedText = "";
      let streamFailed = false;

      const historyPayload = messages
        .filter((m) => m.content.trim())
        .map((m) => ({ role: m.role, content: m.content }));

      try {
        await generateStream(
          query,
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
                        clarifying_questions: meta.clarifying_questions,
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
                        grounding_status: done.grounding_status,
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

      // Fallback to standard generate POST if streaming failed with no text
      if (streamFailed && !accumulatedText) {
        try {
          setError(null);
          const fallbackRes = await generate(query, topK, historyPayload);
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
                    grounding_status: fallbackRes.grounding_status,
                    clarifying_questions: fallbackRes.clarifying_questions,
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
                ? { ...m, content: "⚠️ " + errorMsg }
                : m,
            ),
          );
        }
      }

      setIsGenerating(false);
    },
    [isGenerating],
  );

  return { isGenerating, error, handleSend, clearError };
}
