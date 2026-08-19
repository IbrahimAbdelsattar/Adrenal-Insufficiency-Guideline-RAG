import { useState, useMemo, useCallback, useEffect } from "react";
import type { ChatMessage, ChatSession } from "@/components/ChatView";

const SESSIONS_STORAGE_KEY = "eva_ai_consultation_sessions_v1";
const ACTIVE_SESSION_STORAGE_KEY = "eva_ai_active_session_id_v1";

function createEmptySession(topK: number, title?: string): ChatSession {
  return {
    id: `session-${Date.now()}`,
    title: title || "New Clinical Inquiry",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messages: [],
    topK,
  };
}

function loadSessions(): ChatSession[] | null {
  try {
    const raw = localStorage.getItem(SESSIONS_STORAGE_KEY);
    if (!raw) return null;
    const parsed: ChatSession[] = JSON.parse(raw);
    return parsed.length > 0 ? parsed : null;
  } catch {
    return null;
  }
}

function saveSessions(sessions: ChatSession[]) {
  try {
    localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // Ignore quota errors
  }
}

function loadActiveId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function saveActiveId(id: string) {
  try {
    localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, id);
  } catch {
    // Ignore
  }
}

export interface UseChatSessionsReturn {
  sessions: ChatSession[];
  activeSessionId: string;
  currentSession: ChatSession | undefined;
  messages: ChatMessage[];
  setMessages: (
    updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
  ) => void;
  setActiveSessionId: (id: string) => void;
  handleNewSession: () => void;
  handleDeleteSession: (id: string, e?: React.MouseEvent) => void;
  handleClearAllHistory: () => boolean;
  filteredSessions: (search: string) => ChatSession[];
}

export function useChatSessions(topK: number): UseChatSessionsReturn {
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    return [createEmptySession(topK)];
  });
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [isLoaded, setIsLoaded] = useState(false);

  // Load from localStorage on client mount only to prevent SSR hydration mismatch
  useEffect(() => {
    const loaded = loadSessions();
    const savedActive = loadActiveId();
    if (loaded && loaded.length > 0) {
      setSessions(loaded);
      const active = loaded.find((s) => s.id === savedActive) || loaded[0];
      setActiveSessionId(active.id);
    } else {
      const initial = createEmptySession(topK);
      setSessions([initial]);
      setActiveSessionId(initial.id);
    }
    setIsLoaded(true);
  }, [topK]);

  // Persist sessions to localStorage whenever they change after initial load
  useEffect(() => {
    if (isLoaded && sessions.length > 0) {
      saveSessions(sessions);
    }
  }, [sessions, isLoaded]);

  // Persist activeSessionId to localStorage
  useEffect(() => {
    if (isLoaded && activeSessionId) {
      saveActiveId(activeSessionId);
    }
  }, [activeSessionId, isLoaded]);

  const effectiveSessions = sessions;
  const effectiveActiveId = activeSessionId || sessions[0]?.id || "";

  const currentSession = useMemo(() => {
    return effectiveSessions.find((s) => s.id === effectiveActiveId) || effectiveSessions[0];
  }, [effectiveSessions, effectiveActiveId]);

  const messages = useMemo(() => {
    return currentSession?.messages || [];
  }, [currentSession]);

  const setMessages = useCallback(
    (
      updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
    ) => {
      setSessions((prevSessions) =>
        prevSessions.map((session) => {
          if (session.id === effectiveActiveId) {
            const nextMessages =
              typeof updater === "function" ? updater(session.messages) : updater;
            let nextTitle = session.title;
            if (
              (!nextTitle || nextTitle === "New Clinical Inquiry") &&
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
    },
    [effectiveActiveId],
  );

  const handleNewSession = useCallback(() => {
    const newSession = createEmptySession(topK);
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  }, [topK]);

  const handleDeleteSession = useCallback(
    (sessionIdToDelete: string, e?: React.MouseEvent) => {
      e?.stopPropagation();
      setSessions((prev) => {
        const filtered = prev.filter((s) => s.id !== sessionIdToDelete);
        if (filtered.length === 0) {
          const fresh = createEmptySession(topK);
          setActiveSessionId(fresh.id);
          return [fresh];
        }
        if (effectiveActiveId === sessionIdToDelete) {
          setActiveSessionId(filtered[0].id);
        }
        return filtered;
      });
    },
    [topK, effectiveActiveId],
  );

  const handleClearAllHistory = useCallback((): boolean => {
    if (window.confirm("Are you sure you want to clear all consultation history?")) {
      const fresh = createEmptySession(topK);
      setSessions([fresh]);
      setActiveSessionId(fresh.id);
      return true;
    }
    return false;
  }, [topK]);

  const filteredSessions = useCallback(
    (search: string): ChatSession[] => {
      if (!search.trim()) return effectiveSessions;
      const q = search.toLowerCase();
      return effectiveSessions.filter(
        (s) =>
          s.title.toLowerCase().includes(q) ||
          s.messages.some((m) => m.content.toLowerCase().includes(q)),
      );
    },
    [effectiveSessions],
  );

  return {
    sessions: effectiveSessions,
    activeSessionId: effectiveActiveId,
    currentSession,
    messages,
    setMessages,
    setActiveSessionId,
    handleNewSession,
    handleDeleteSession,
    handleClearAllHistory,
    filteredSessions,
  };
}
