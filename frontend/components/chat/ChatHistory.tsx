"use client";

import { useState, useMemo } from "react";
import type { ChatSession } from "@/components/ChatView";
import { exportSessionToMarkdown } from "./SessionExport";

interface ChatHistoryProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e?: React.MouseEvent) => void;
  onClearAll: () => boolean;
  onClose: () => void;
  t: Record<string, unknown>;
}

export function ChatHistory({
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
  onClearAll,
  onClose,
  t,
}: ChatHistoryProps) {
  const [search, setSearch] = useState("");
  const typedT = t as Record<string, string>;

  const filteredSessions = useMemo(() => {
    if (!search.trim()) return sessions;
    const q = search.toLowerCase();
    return sessions.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.messages.some((m) => m.content.toLowerCase().includes(q)),
    );
  }, [sessions, search]);

  const handleSelect = (id: string) => {
    onSelectSession(id);
    onClose();
  };

  return (
    <div className="mono-card rounded-2xl p-4 border border-accent-bright/30 bg-card/95 shadow-xl animate-fade-in-up space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line/40 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-base">📜</span>
          <h3 className="text-sm font-extrabold text-ink">
            {typedT.consultationHistory || "Consultation History"}
          </h3>
          <span className="text-xs text-ink-faint">
            ({sessions.length} {typedT.historySessionsCount || "sessions"})
          </span>
        </div>
        <div className="flex items-center gap-2">
          {sessions.length > 1 && (
            <button
              type="button"
              onClick={() => onClearAll()}
              className="text-[11px] text-caution hover:underline cursor-pointer"
            >
              {typedT.clearAllHistory || "Clear All"}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="mono-button h-6 w-6 flex items-center justify-center rounded-lg text-ink-dim hover:text-ink text-xs font-bold cursor-pointer"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={
            typedT.searchHistoryPlaceholder || "Search previous consultations..."
          }
          className="w-full rounded-xl bg-transparent px-3 py-1.5 text-xs text-ink placeholder:text-ink-faint focus:outline-none mono-inset"
        />
      </div>

      {/* Session Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 max-h-[260px] overflow-y-auto pr-1">
        {filteredSessions.length === 0 ? (
          <div className="col-span-full py-6 text-center text-xs text-ink-dim">
            {typedT.noHistoryFound || "No previous consultations found"}
          </div>
        ) : (
          filteredSessions.map((session) => {
            const isActive = session.id === activeSessionId;
            const messageCount = session.messages.length;
            return (
              <div
                key={session.id}
                onClick={() => handleSelect(session.id)}
                className={`mono-card-interactive p-3 rounded-xl flex flex-col justify-between gap-2 text-left cursor-pointer transition-all ${
                  isActive
                    ? "border-accent-bright/60 bg-accent-bright/10 shadow-sm"
                    : "border-line/40 hover:border-line"
                }`}
              >
                <div className="flex items-start justify-between gap-1.5">
                  <h4 className="text-xs font-bold text-ink line-clamp-2 leading-snug">
                    {session.title || typedT.untitledSession || "Untitled"}
                  </h4>
                  {isActive && (
                    <span className="mono-pill px-1.5 py-0.2 text-[9px] font-extrabold text-accent-bright shrink-0">
                      {typedT.activeSession || "Active"}
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-between text-[10px] text-ink-faint border-t border-line/30 pt-1.5 mt-1">
                  <span>
                    {new Date(session.updatedAt || session.createdAt).toLocaleDateString([], {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span>💬 {messageCount}</span>
                    <button
                      type="button"
                      title={typedT.exportSession || "Export Summary"}
                      onClick={(e) => {
                        e.stopPropagation();
                        exportSessionToMarkdown(session);
                      }}
                      className="hover:text-accent-bright p-0.5 rounded transition-colors"
                    >
                      📥
                    </button>
                    <button
                      type="button"
                      title={typedT.deleteSession || "Delete"}
                      onClick={(e) => onDeleteSession(session.id, e)}
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
  );
}
