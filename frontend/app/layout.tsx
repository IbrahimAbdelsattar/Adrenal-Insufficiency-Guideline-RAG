"use client";

import { useEffect, useState } from "react";
import "./globals.css";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LanguageToggle } from "@/components/LanguageToggle";
import { translations, type Language } from "@/lib/translations";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [lang, setLang] = useState<Language>("en");

  useEffect(() => {
    const savedLang = localStorage.getItem("eva_lang") as Language | null;
    if (savedLang && (savedLang === "en" || savedLang === "ar")) {
      setLang(savedLang);
    }
    const handleLangChange = (e: Event) => {
      const customEvent = e as CustomEvent<Language>;
      if (customEvent.detail) setLang(customEvent.detail);
    };
    window.addEventListener("languageChange", handleLangChange);
    return () => window.removeEventListener("languageChange", handleLangChange);
  }, []);

  const t = translations[lang];

  return (
    <html lang={lang} dir={lang === "ar" ? "rtl" : "ltr"} className="dark" suppressHydrationWarning>
      <head>
        <title>Eva AI — Clinical Decision Support</title>
        <meta
          name="description"
          content="Eva AI evidence retrieval over official NICE clinical guidelines with page-level citation traceability."
        />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var savedTheme = localStorage.getItem('eva_theme');
                  var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                  var theme = savedTheme || (prefersDark ? 'dark' : 'light');
                  if (theme === 'dark') {
                    document.documentElement.classList.add('dark');
                    document.documentElement.classList.remove('light');
                  } else {
                    document.documentElement.classList.add('light');
                    document.documentElement.classList.remove('dark');
                  }

                  var savedLang = localStorage.getItem('eva_lang') || 'en';
                  document.documentElement.setAttribute('lang', savedLang);
                  document.documentElement.setAttribute('dir', savedLang === 'ar' ? 'rtl' : 'ltr');
                } catch (e) {}
              })();
            `,
          }}
        />
      </head>
      <body className="min-h-screen bg-ground text-ink antialiased selection:bg-accent-deep selection:text-white" suppressHydrationWarning>
        {/* Eva AI Header */}
        <header className="sticky top-0 z-40 border-b border-line/60 bg-ground/90 backdrop-blur-md transition-colors duration-300">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3.5 sm:px-6">
            {/* Eva AI Brand Identity */}
            <div className="flex items-center gap-4">
              <div className="mono-card relative flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-surface-2 to-surface text-accent-bright shadow-lg border border-accent-bright/20">
                <span className="font-brand-cursive text-2xl text-accent-bright drop-shadow">E</span>
                <span className="font-brand-serif text-xs font-bold tracking-widest text-accent-bright -ml-0.5">A</span>
                <span className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-bright opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-accent-bright"></span>
                </span>
              </div>
              <div>
                <div className="flex items-baseline gap-2">
                  <h1 className="text-xl tracking-wide text-ink">
                    <span className="font-brand-cursive text-2xl font-normal text-accent-bright me-1.5">Eva</span>
                    <span className="font-brand-serif font-bold text-accent-bright tracking-widest text-lg">AI</span>
                  </h1>
                  <span className="mono-pill px-2.5 py-0.5 text-[10px] font-mono font-bold text-accent-bright uppercase tracking-wider">
                    {t.tagline}
                  </span>
                </div>
                <p className="text-xs font-medium text-ink-dim">
                  {t.brandSubtitle}
                </p>
              </div>
            </div>

            {/* Header Right Controls (Language & Theme Toggles) */}
            <div className="flex items-center gap-3">
              <div className="hidden items-center gap-2 text-xs text-ink-faint sm:flex">
                <span className="mono-inset px-2.5 py-1 font-mono text-[11px] font-semibold text-accent-bright shadow-inner rounded-lg">
                  Ctrl + K
                </span>
                <span>{t.shortcutHint}</span>
              </div>

              <div className="mono-pill flex items-center gap-2.5 rounded-full px-3.5 py-1.5 text-xs font-medium text-ink-dim">
                <span className="h-2 w-2 rounded-full bg-accent-bright animate-mono-pulse" />
                <span className="hidden sm:inline text-ink-faint">{t.modeLabel}</span>
                <span className="text-accent-bright font-bold">{t.modeValue}</span>
              </div>

              {/* Language Switcher Button */}
              <LanguageToggle onLanguageChange={setLang} />

              {/* Theme Toggle Button */}
              <ThemeToggle />
            </div>
          </div>
        </header>

        {/*
          Constitution Principle IV / FR-029:
          Monomorphic Inset Clinical Disclaimer Banner
        */}
        <div className="mono-inset border-y border-caution/20 bg-caution/[0.04]">
          <div className="mx-auto flex max-w-7xl items-start gap-3 px-4 py-3 sm:px-6">
            <div className="mono-pill flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-caution">
              <svg
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
            <p className="text-xs leading-relaxed text-caution/90">
              <strong className="font-bold text-caution">{t.disclaimerTitle}</strong>{" "}
              {t.disclaimerBody}
            </p>
          </div>
        </div>

        {/* Main Monomorphic Layout Container */}
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>

        {/* Eva AI Monomorphic Footer */}
        <footer className="mt-16 border-t border-line/60 bg-ground/80 py-8 text-center text-xs text-ink-faint">
          <div className="mx-auto max-w-7xl px-4 sm:px-6">
            <p className="font-semibold text-ink-dim">
              <span className="font-brand-cursive text-sm text-accent-bright me-1">Eva</span>
              <span className="font-brand-serif text-accent-bright font-bold me-2">AI</span>
              · {t.footerText}
            </p>
            <p className="mt-1 text-ink-faint">
              {t.footerSub}
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
