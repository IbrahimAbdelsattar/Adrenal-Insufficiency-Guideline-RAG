"use client";

import { useRef, useEffect } from "react";

interface ChatComposerProps {
  inputQuery: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  isGenerating: boolean;
  t: Record<string, unknown>;
}

export function ChatComposer({
  inputQuery,
  onInputChange,
  onSend,
  onKeyDown,
  isGenerating,
  t,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const typedT = t as Record<string, string>;

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  }, []);

  return (
    <div className="mono-card rounded-2xl p-3 sm:p-4 space-y-3">
      <div className="relative">
        <textarea
          ref={textareaRef}
          rows={2}
          value={inputQuery}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={isGenerating}
          placeholder={
            typedT.chatPlaceholder ||
            "Ask Eva AI a clinical question based on NICE NG243..."
          }
          className="w-full resize-none rounded-xl bg-transparent px-3.5 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none mono-inset"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="text-[11px] text-ink-faint hidden sm:inline">
          {typedT.shortcutSend || "Press Enter ↵ to send, Shift+Enter for new line"}
        </span>

        <div className="flex items-center gap-2 ml-auto">
          <button
            type="button"
            onClick={onSend}
            disabled={!inputQuery.trim() || isGenerating}
            className={`mono-button-primary flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-extrabold text-white transition-all cursor-pointer ${
              !inputQuery.trim() || isGenerating
                ? "opacity-50 cursor-not-allowed"
                : "shadow-md hover:scale-[1.02]"
            }`}
          >
            {isGenerating ? (
              <>
                <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
                <span>{typedT.generatingBtn || "Generating..."}</span>
              </>
            ) : (
              <>
                <span>{typedT.sendBtn || "Send"}</span>
                <span>↵</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
