"use client";

import { useState, useMemo } from "react";
import { ChunkCard } from "@/components/ChunkCard";
import { IndexStatus } from "@/components/IndexStatus";
import { SearchBox } from "@/components/SearchBox";
import { search } from "@/lib/api";
import type { SearchResponse } from "@/lib/api";

type FilterMode = "all" | "high" | "floor" | "caution";

export default function Page() {
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topK, setTopK] = useState(5);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");

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
      {/* Main Content Area */}
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
          <div className="glass-panel rounded-2xl border-caution/40 bg-caution/10 p-5 text-caution animate-fade-in-up">
            <div className="flex items-center gap-2 font-bold text-sm">
              <svg className="h-5 w-5 text-caution" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>Search Error</span>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-caution/90">{error}</p>
          </div>
        )}

        {/* Loading Skeleton State */}
        {loading && (
          <div className="space-y-4" aria-busy="true">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-44 rounded-2xl border border-line/60 bg-surface/50 p-6 skeleton-shimmer"
              />
            ))}
          </div>
        )}

        {/* Search Results Area */}
        {!loading && response && (
          <section className="space-y-5 animate-fade-in-up">
            {/* Search Metadata & Filter Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-line/60 bg-surface-2/40 px-4 py-3 text-xs">
              <div className="flex items-center gap-2 text-ink-dim">
                <span className="font-bold text-ink">
                  {response.result_count}
                </span>
                <span>chunks returned</span>
                <span>·</span>
                <span className="text-accent-bright font-semibold">
                  {aboveFloorCount} above floor
                </span>
                <span>·</span>
                <span className="font-mono text-cyan-400">⚡ {response.latency_ms} ms</span>
              </div>

              {/* Filter Tabs */}
              <div className="flex items-center gap-1 rounded-lg bg-surface p-1 border border-line">
                <FilterButton
                  active={filterMode === "all"}
                  onClick={() => setFilterMode("all")}
                  label={`All (${response.results.length})`}
                />
                <FilterButton
                  active={filterMode === "high"}
                  onClick={() => setFilterMode("high")}
                  label="High Confidence (≥75%)"
                />
                {response.results.some((r) => r.below_floor) && (
                  <FilterButton
                    active={filterMode === "floor"}
                    onClick={() => setFilterMode("floor")}
                    label="Below Floor"
                  />
                )}
              </div>
            </div>

            {/* Warning if no strong evidence found */}
            {!response.evidence_found && (
              <div className="glass-panel rounded-2xl border-caution/40 bg-caution/10 p-5 text-caution">
                <div className="flex items-center gap-2 font-bold text-sm">
                  <svg className="h-5 w-5 text-caution" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>No Strong Evidence Above Floor</span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-caution/90">
                  No retrieved chunk cleared the relevance threshold (floor = 0.30). The ingested guidelines may not explicitly answer this question. Low-scoring chunks are displayed below for visual inspection.
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
                <div className="rounded-2xl border border-dashed border-line/80 p-8 text-center text-xs text-ink-faint">
                  No chunks match the selected filter category ({filterMode}).
                </div>
              )}
            </div>
          </section>
        )}

        {/* Empty State / Initial Overview */}
        {!loading && !response && !error && (
          <div className="glass-panel rounded-2xl border-dashed border-line/80 p-12 text-center animate-fade-in-up">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-deep/20 text-accent-bright border border-accent-bright/30">
              <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <h2 className="mt-4 text-base font-bold text-ink">
              Clinical Evidence Inspector Ready
            </h2>
            <p className="mt-1.5 max-w-md mx-auto text-xs leading-relaxed text-ink-dim">
              Submit a natural-language clinical query or select one of the quick exemplars above to inspect section-aware guideline chunks and exact page citations.
            </p>

            <div className="mt-8 grid grid-cols-1 gap-4 text-left sm:grid-cols-3">
              <FeatureCard
                icon="📜"
                title="Strict Citation Trail"
                desc="Every chunk includes document name, source page, section title, and publication year."
              />
              <FeatureCard
                icon="⚡"
                title="Dense Vector Search"
                desc="Powered by 1536-dim OpenRouter embeddings & persistent ChromaDB vector store."
              />
              <FeatureCard
                icon="🛡️"
                title="Clinical Governance"
                desc="Atomic recommendations are never split across chunk boundaries."
              />
            </div>
          </div>
        )}
      </div>

      {/* Sidebar: Knowledge Base & Source Status */}
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
      className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition-all ${
        active
          ? "bg-accent-deep text-white shadow-sm"
          : "text-ink-faint hover:text-ink hover:bg-surface-2"
      }`}
    >
      {label}
    </button>
  );
}

function FeatureCard({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="rounded-xl border border-line/60 bg-surface-2/40 p-4">
      <div className="text-xl">{icon}</div>
      <h3 className="mt-2 text-xs font-bold text-ink">{title}</h3>
      <p className="mt-1 text-[11px] leading-relaxed text-ink-faint">{desc}</p>
    </div>
  );
}
