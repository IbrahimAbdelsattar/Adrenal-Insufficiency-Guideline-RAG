"use client";

import { useEffect, useState } from "react";
import { getIndexStatus, getSources } from "@/lib/api";
import type { IndexManifest, SourceDocument } from "@/lib/api";
import { translations, type Language } from "@/lib/translations";

export function IndexStatus() {
  const [manifest, setManifest] = useState<IndexManifest | null>(null);
  const [sources, setSources] = useState<SourceDocument[]>([]);
  const [retrieverMode, setRetrieverMode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  useEffect(() => {
    import("@/lib/api").then(({ getHealth }) => {
      getHealth()
        .then((h) => setRetrieverMode(h.retriever_type || null))
        .catch(() => {});
    });
    getIndexStatus()
      .then(setManifest)
      .catch((e) => setError(e.message));
    getSources()
      .then((r) => setSources(r.sources))
      .catch(() => setSources([]));
  }, []);

  if (error) {
    return (
      <aside className="mono-card rounded-2xl p-5 border-caution/40 text-sm text-caution">
        <div className="flex items-center gap-2 font-bold">
          <svg className="h-4 w-4 text-caution" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{t.indexNotReady}</span>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-caution/80">{error}</p>
        <p className="mt-3 text-[11px] font-mono text-caution/70">{t.runIngestHint}</p>
      </aside>
    );
  }

  if (!manifest) {
    return (
      <aside className="mono-card rounded-2xl p-5 text-xs text-ink-faint">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 animate-spin text-accent-bright" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span>{t.loadingMeta}</span>
        </div>
      </aside>
    );
  }

  const built = new Date(manifest.built_at).toLocaleString(lang === "ar" ? "ar-SA" : "en-US");

  return (
    <aside className="mono-card space-y-5 rounded-2xl p-5">
      {/* Eva AI Store Header & Monomorphic Pulse Badge */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <h2 className="text-xs font-extrabold uppercase tracking-wider text-ink-dim">
            {t.storeTitle}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {retrieverMode && (
            <span className="mono-pill px-2.5 py-0.5 text-[10px] font-mono font-bold text-ink-dim uppercase tracking-wider">
              Mode: {retrieverMode}
            </span>
          )}
          <span className="mono-pill flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-mono font-bold text-accent-bright uppercase tracking-wider">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-bright animate-mono-pulse" />
            {t.activeBadge}
          </span>
        </div>
      </div>

      {/* Extruded Metrics Grid */}
      <dl className="grid grid-cols-2 gap-3">
        <Stat label={t.docsStat} value={String(manifest.document_count)} sub={t.docsSub} />
        <Stat label={t.chunksStat} value={String(manifest.chunk_count)} sub={t.chunksSub} />
      </dl>

      {/* Monomorphic Inset Metadata Rows */}
      <div className="mono-inset space-y-2 rounded-xl p-3.5 text-xs">
        <Row label={t.embedModelRow} value={manifest.embedding_model} mono />
        <Row label={t.dimsRow} value={`${manifest.embedding_dimensions}`} mono />
        <Row
          label={t.tokenBudgetRow}
          value={`${manifest.chunk_min_tokens}–${manifest.chunk_max_tokens}`}
          mono
        />
        <Row label={t.lastBuildRow} value={built} />
      </div>

      {/* Registered Guidelines Section */}
      {sources.length > 0 && (
        <div className="border-t border-line/60 pt-4">
          <h3 className="flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-wider text-ink-dim">
            <svg className="h-3.5 w-3.5 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            {t.registeredGuidelines}
          </h3>
          <ul className="mt-3 space-y-3">
            {sources.map((source) => (
              <li
                key={source.doc_id}
                className="mono-card-interactive rounded-xl p-3 text-xs"
              >
                <a
                  href={source.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="font-extrabold text-ink hover:text-accent-bright transition-colors flex items-center justify-between gap-1"
                >
                  <span className="line-clamp-2">{source.document_name}</span>
                  <svg className="h-3.5 w-3.5 shrink-0 text-accent-bright" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-1 text-[11px] text-ink-faint">
                  <span>{source.publisher}</span>
                  <span className="mono-inset px-2 py-0.5 font-mono font-bold text-accent-bright rounded-md">
                    {source.publication_year}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="mono-card rounded-xl p-3 border border-accent-bright/10">
      <dt className="text-[10px] font-extrabold uppercase tracking-wider text-ink-faint">
        {label}
      </dt>
      <dd className="mt-1 text-2xl font-black tabular-nums text-ink">
        {value}
      </dd>
      {sub && <p className="mt-0.5 text-[10px] text-ink-faint">{sub}</p>}
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="shrink-0 text-ink-faint">{label}</span>
      <span
        className={`truncate text-end text-accent-bright ${mono ? "font-mono font-bold" : ""}`}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}
