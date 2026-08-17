"use client";

import { useState, useMemo, useEffect } from "react";
import { ChunkCard } from "@/components/ChunkCard";
import { IndexStatus } from "@/components/IndexStatus";
import { SearchBox } from "@/components/SearchBox";
import { search } from "@/lib/api";
import type { SearchResponse } from "@/lib/api";
import { translations, type Language } from "@/lib/translations";

type FilterMode = "all" | "high" | "floor" | "caution";

export default function Page() {
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topK, setTopK] = useState(5);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
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

  async function runSearch(query: string) {
    setLoading(true);
    setError(null);
    try {
      setResponse(await search(query, topK));
      setFilterMode("all");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search request failed.");
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }

  const aboveFloorCount = useMemo(() => {
    return response?.results.filter((r) => !r.below_floor).length ?? 0;
  }, [response]);

  const filteredResults = useMemo(() => {
    if (!response) return [];
    if (filterMode === "high") {
      return response.results.filter((r) => r.score >= 0.75 && !r.below_floor);
    }
    if (filterMode === "floor") {
      return response.results.filter((r) => r.below_floor);
    }
    if (filterMode === "caution") {
      return response.results.filter((r) => r.chunk.requires_caution);
    }
    return response.results;
  }, [response, filterMode]);

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_22rem]">
      {/* Main Eva AI Area */}
      <div className="min-w-0 space-y-6">
        {/* Search Component */}
        <SearchBox
          onSearch={runSearch}
          loading={loading}
          topK={topK}
          onTopKChange={setTopK}
        />

        {/* Error Surface */}
        {error && (
          <div className="mono-card rounded-2xl border-caution/40 bg-caution/5 p-5 text-caution animate-fade-in-up">
            <div className="flex items-center gap-2 font-bold text-sm">
              <svg className="h-5 w-5 text-caution" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>{t.searchErrorTitle}</span>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-caution/90">{error}</p>
          </div>
        )}

        {/* Monomorphic Loading State */}
        {loading && (
          <div className="space-y-4" aria-busy="true">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="mono-card h-44 rounded-2xl p-6 skeleton-shimmer"
              />
            ))}
          </div>
        )}

        {/* Search Results Area */}
        {!loading && response && (
          <section className="space-y-5 animate-fade-in-up">
            {/* Eva AI Toolbar */}
            <div className="mono-card flex flex-wrap items-center justify-between gap-4 rounded-2xl p-3.5 text-xs">
              <div className="flex items-center gap-2.5 text-ink-dim">
                <span className="mono-pill px-2.5 py-1 font-mono font-extrabold text-ink">
                  {response.result_count} {t.resultCount}
                </span>
                <span>·</span>
                <span className="font-semibold text-accent-bright">
                  {aboveFloorCount} {t.aboveFloor}
                </span>
                <span>·</span>
                <span className="font-mono text-accent-bright font-bold">⚡ {response.latency_ms} ms</span>
              </div>

              {/* Monomorphic Filter Tabs */}
              <div className="mono-inset flex items-center gap-1 rounded-xl p-1">
                <FilterButton
                  active={filterMode === "all"}
                  onClick={() => setFilterMode("all")}
                  label={`${t.filterAll} (${response.results.length})`}
                />
                <FilterButton
                  active={filterMode === "high"}
                  onClick={() => setFilterMode("high")}
                  label={t.filterHigh}
                />
                {response.results.some((r) => r.below_floor) && (
                  <FilterButton
                    active={filterMode === "floor"}
                    onClick={() => setFilterMode("floor")}
                    label={t.filterFloor}
                  />
                )}
              </div>
            </div>

            {/* Warning if no strong evidence found */}
            {!response.evidence_found && (
              <div className="mono-card rounded-2xl border-caution/40 bg-caution/5 p-5 text-caution">
                <div className="flex items-center gap-2 font-bold text-sm">
                  <svg className="h-5 w-5 text-caution" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{t.noEvidenceTitle}</span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-caution/90">
                  {t.noEvidenceBody}
                </p>
              </div>
            )}

            {/* List of Retrieved Chunks */}
            <div className="space-y-4">
              {filteredResults.length > 0 ? (
                filteredResults.map((result) => (
                  <ChunkCard key={result.chunk.chunk_id} result={result} />
                ))
              ) : (
                <div className="mono-inset rounded-2xl p-8 text-center text-xs text-ink-faint">
                  {t.noMatchFilter} ({filterMode}).
                </div>
              )}
            </div>
          </section>
        )}

        {/* Eva AI Empty State */}
        {!loading && !response && !error && (
          <div className="mono-card rounded-2xl p-10 text-center animate-fade-in-up">
            <div className="mono-button mx-auto flex h-16 w-16 items-center justify-center rounded-2xl text-accent-bright border border-accent-bright/20 shadow-md">
              <span className="font-brand-cursive text-3xl text-accent-bright drop-shadow">E</span>
              <span className="font-brand-serif text-sm font-bold text-accent-bright -ml-0.5">A</span>
            </div>
            <h2 className="mt-5 text-lg font-extrabold text-ink tracking-wide">
              <span className="font-brand-cursive text-2xl font-normal text-accent-bright me-1">Eva</span>
              <span className="font-brand-serif text-accent-bright me-2">AI</span> {t.inspectorReadyTitle}
            </h2>
            <p className="mt-1.5 max-w-md mx-auto text-xs leading-relaxed text-ink-dim">
              {t.inspectorReadyBody}
            </p>

            <div className="mt-8 grid grid-cols-1 gap-4 text-left sm:grid-cols-3">
              <FeatureCard
                icon="📜"
                title={t.feat1Title}
                desc={t.feat1Desc}
              />
              <FeatureCard
                icon="💎"
                title={t.feat2Title}
                desc={t.feat2Desc}
              />
              <FeatureCard
                icon="🛡️"
                title={t.feat3Title}
                desc={t.feat3Desc}
              />
            </div>
          </div>
        )}
      </div>

      {/* Monomorphic Sidebar */}
      <IndexStatus />
    </div>
  );
}

function FilterButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg px-3 py-1.5 text-[11px] font-extrabold transition-all cursor-pointer ${
        active
          ? "mono-button-primary text-white"
          : "mono-button text-ink-faint hover:text-ink"
      }`}
    >
      {label}
    </button>
  );
}

function FeatureCard({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="mono-card-interactive rounded-xl p-4">
      <div className="text-2xl">{icon}</div>
      <h3 className="mt-2 text-xs font-bold text-ink">{title}</h3>
      <p className="mt-1 text-[11px] leading-relaxed text-ink-faint">{desc}</p>
    </div>
  );
}
