import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clinical Decision Support Lite — Adrenal Insufficiency Guideline RAG",
  description:
    "Evidence-grounded retrieval over official NICE clinical guidelines with page-level citation traceability.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-ground text-ink antialiased selection:bg-accent-deep selection:text-white">
        {/* Main Application Header */}
        <header className="sticky top-0 z-40 border-b border-line/80 bg-surface/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3.5 sm:px-6">
            {/* Brand Logo & Context */}
            <div className="flex items-center gap-3.5">
              <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-accent-deep to-accent text-ground shadow-lg shadow-accent/20">
                <svg
                  className="h-5 w-5 fill-current"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path d="M19 3H5c-1.1 0-1.99.9-1.99 2L3 19c0 1.1.89 2 1.99 2H19c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-1 11h-4v4h-4v-4H6v-4h4V6h4v4h4v4z" />
                </svg>
                <span className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-bright opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-accent-bright"></span>
                </span>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-base font-bold tracking-tight text-ink">
                    Clinical Decision Support Lite
                  </h1>
                  <span className="rounded-full border border-accent-bright/30 bg-accent-bright/10 px-2 py-0.5 text-[10px] font-semibold text-accent-bright uppercase tracking-wider">
                    v1.0 Baseline
                  </span>
                </div>
                <p className="text-xs font-medium text-ink-dim">
                  Adrenal Insufficiency Management · NICE Guideline NG243
                </p>
              </div>
            </div>

            {/* Header Right Badges & Shortcuts */}
            <div className="flex items-center gap-3">
              <div className="hidden items-center gap-2 text-xs text-ink-faint sm:flex">
                <span className="rounded-md border border-line bg-surface-2 px-2 py-1 font-mono text-[11px] text-ink-dim shadow-inner">
                  Ctrl + K
                </span>
                <span>to search</span>
              </div>

              <div className="flex items-center gap-2 rounded-full border border-line bg-surface-2/60 px-3.5 py-1.5 text-xs font-medium text-ink-dim">
                <span className="h-2 w-2 rounded-full bg-accent-bright animate-pulse" />
                <span className="hidden sm:inline">Constitution Mode:</span>
                <span className="text-accent-bright font-semibold">Retrieval Only</span>
              </div>
            </div>
          </div>
        </header>

        {/*
          Constitution Principle IV / FR-029:
          Mandatory Clinical Disclaimer Banner
        */}
        <div className="border-b border-caution/30 bg-gradient-to-r from-caution/10 via-caution/5 to-transparent">
          <div className="mx-auto flex max-w-7xl items-start gap-3 px-4 py-2.5 sm:px-6">
            <svg
              className="mt-0.5 h-4 w-4 shrink-0 text-caution"
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
            <p className="text-xs leading-relaxed text-caution/95">
              <strong className="font-semibold text-caution">Clinical Decision Support Aid:</strong>{" "}
              This research prototype provides evidence retrieval from registered official guidelines only.
              It is not a diagnostic tool or emergency service. All retrieved evidence must be evaluated by a qualified medical professional.
            </p>
          </div>
        </div>

        {/* Main Application Container */}
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>

        {/* Footer */}
        <footer className="mt-16 border-t border-line/60 bg-surface/40 py-8 text-center text-xs text-ink-faint">
          <div className="mx-auto max-w-7xl px-4 sm:px-6">
            <p className="font-medium text-ink-dim">
              Evidence Grounded · Structural Citations · Non-Modifying Retrieval Pipeline
            </p>
            <p className="mt-1 text-ink-faint">
              Every result traces directly to an official registered PDF, page number, and recommendation section.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
