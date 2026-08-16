"use client";

import { useEffect, useState } from "react";
import type { Language } from "@/lib/translations";

export function LanguageToggle({
  onLanguageChange,
}: {
  onLanguageChange?: (lang: Language) => void;
}) {
  const [lang, setLang] = useState<Language>("en");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const savedLang = localStorage.getItem("sapphire_lang") as Language | null;
    if (savedLang && (savedLang === "en" || savedLang === "ar")) {
      setLang(savedLang);
      applyLang(savedLang);
    }
  }, []);

  function applyLang(newLang: Language) {
    const root = document.documentElement;
    root.setAttribute("lang", newLang);
    root.setAttribute("dir", newLang === "ar" ? "rtl" : "ltr");
    if (onLanguageChange) onLanguageChange(newLang);
    // Dispatch custom event for dynamic components
    window.dispatchEvent(new CustomEvent("languageChange", { detail: newLang }));
  }

  function toggleLang() {
    const nextLang = lang === "en" ? "ar" : "en";
    setLang(nextLang);
    localStorage.setItem("sapphire_lang", nextLang);
    applyLang(nextLang);
  }

  if (!mounted) {
    return (
      <div className="h-9 w-14 rounded-xl border border-line/60 bg-surface/50 opacity-0" />
    );
  }

  return (
    <button
      type="button"
      onClick={toggleLang}
      className="mono-button flex h-9 items-center gap-1.5 rounded-xl px-3 text-xs font-bold text-accent-bright transition-all cursor-pointer"
      title={`Switch to ${lang === "en" ? "Arabic (العربية)" : "English"}`}
      aria-label="Toggle language"
    >
      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"
        />
      </svg>
      <span>{lang === "en" ? "العربية" : "EN"}</span>
    </button>
  );
}
