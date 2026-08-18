"use client";

import { useState, useMemo, useEffect } from "react";
import { ChunkCard } from "@/components/ChunkCard";
import { AnswerCard } from "@/components/AnswerCard";
import { IndexStatus } from "@/components/IndexStatus";
import { SearchBox } from "@/components/SearchBox";
import { search, generate, generateStream } from "@/lib/api";
import type { SearchResponse, GenerateResponse } from "@/lib/api";
import { translations, type Language } from "@/lib/translations";

type FilterMode = "all" | "high" | "floor" | "caution";

export default function Page() {
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [genResponse, setGenResponse] = useState<GenerateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topK, setTopK] = useState(5);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [mode, setMode] = useState<"search" | "generate">("search");
  const [lang, setLang] = useState<Language>("en");

  useEffect(() => {
    const savedLang = localStorage.getItem("eva_lang") as Language | null;

    if (savedLang && (savedLang === "en" || savedLang === "ar")) {
      setLang(savedLang);
    }

    const handleLangChange = (e: Event) => {
      const customEvent = e as CustomEvent<Language>;

      if (customEvent.detail) {
        setLang(customEvent.detail);
      }
    };

    window.addEventListener("languageChange", handleLangChange);

    return () => {
      window.removeEventListener("languageChange", handleLangChange);
    };
  }, []);

  const t = translations[lang];

  /*
   * ------------------------------------------------------------
   * Search & Generate Handler
   * ------------------------------------------------------------
   */

  async function runSearch(query: string) {
    setError(null);
    setResponse(null);
    setGenResponse(null);

    try {
      if (mode === "search") {
        setLoading(true);
        const result = await search(query, topK);
        setResponse(result);
        setFilterMode("all");
      } else {
        setStreaming(true);
        setGenResponse({
          query,
          answer: "",
          citations: [],
          evidence_found: false,
          disclaimer: "",
          model: "",
          latency_ms: 0,
        });

        let accumulated = "";
        let streamFailed = false;

        try {
          await generateStream(query, topK, {
            onMeta: (meta) =>
              setGenResponse((prev) =>
                prev
                  ? {
                      ...prev,
                      model: meta.model,
                      evidence_found: meta.evidence_found,
                      cache_hit: meta.cache_hit,
                    }
                  : prev,
              ),
            onToken: (text) => {
              accumulated += text;
              const snapshot = accumulated;

              setGenResponse((prev) =>
                prev ? { ...prev, answer: snapshot } : prev,
              );
            },
            onDone: (done) =>
              setGenResponse((prev) =>
                prev
                  ? {
                      ...prev,
                      citations: done.citations,
                      latency_ms: done.latency_ms,
                      disclaimer: done.disclaimer,
                    }
                  : prev,
              ),
            onError: (detail) => {
              streamFailed = true;
              setError(detail);
            },
          });
        } catch {
          streamFailed = true;
        }

        // If streaming failed and nothing was received, fallback to standard generate API
        if (streamFailed && !accumulated) {
          try {
            setError(null);
            const fallbackResult = await generate(query, topK);
            setGenResponse(fallbackResult);
          } catch (fallbackError) {
            setGenResponse(null);
            setError(
              fallbackError instanceof Error
                ? fallbackError.message
                : "Generation failed."
            );
          }
        }
      }
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Request failed."
      );
    } finally {
      setLoading(false);
      setStreaming(false);
    }
  }

  /*
   * ------------------------------------------------------------
   * Response State
   * ------------------------------------------------------------
   */

  const isOutOfScope =
    response?.scope_status === "out_of_scope";

  const isInScope =
    response?.scope_status === "in_scope";

  const hasNoEvidence =
    response?.scope_status === "no_evidence";

  /*
   * ------------------------------------------------------------
   * Evidence Count
   * ------------------------------------------------------------
   */

  const aboveFloorCount = useMemo(() => {
    return (
      response?.results.filter(
        (r) => !r.below_floor
      ).length ?? 0
    );
  }, [response]);

  /*
   * ------------------------------------------------------------
   * Result Filters
   * ------------------------------------------------------------
   */

  const filteredResults = useMemo(() => {
    if (!response) {
      return [];
    }

    if (filterMode === "high") {
      return response.results.filter(
        (r) =>
          r.score >= 0.75 &&
          !r.below_floor
      );
    }

    if (filterMode === "floor") {
      return response.results.filter(
        (r) => r.below_floor
      );
    }

    if (filterMode === "caution") {
      return response.results.filter(
        (r) => r.chunk.requires_caution
      );
    }

    return response.results;
  }, [response, filterMode]);

  /*
   * ------------------------------------------------------------
   * UI
   * ------------------------------------------------------------
   */

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_22rem]">

      {/* ====================================================== */}
      {/* Main Eva AI Area                                      */}
      {/* ====================================================== */}

      <div className="min-w-0 space-y-6">

        {/* ---------------------------------------------------- */}
        {/* Search & Mode Switch Component                       */}
        {/* ---------------------------------------------------- */}

        <SearchBox
          onSearch={runSearch}
          loading={loading || streaming}
          topK={topK}
          onTopKChange={setTopK}
          mode={mode}
          onModeChange={setMode}
        />

        {/* ---------------------------------------------------- */}
        {/* Error Surface                                       */}
        {/* ---------------------------------------------------- */}

        {error && (
          <div className="mono-card rounded-2xl border-caution/40 bg-caution/5 p-5 text-caution animate-fade-in-up">

            <div className="flex items-center gap-2 font-bold text-sm">

              <svg
                className="h-5 w-5 text-caution"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.33-2.694-1.333-3.464 0L3.34 16c-.77 1.33.192 3 1.732 3z"
                />
              </svg>

              <span>
                {t.searchErrorTitle}
              </span>

            </div>

            <p className="mt-1.5 text-xs leading-relaxed text-caution/90">
              {error}
            </p>

          </div>
        )}

        {/* ---------------------------------------------------- */}
        {/* Loading State                                        */}
        {/* ---------------------------------------------------- */}

        {loading && (
          <div
            className="space-y-4"
            aria-busy="true"
          >
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="mono-card h-44 rounded-2xl p-6 skeleton-shimmer"
              />
            ))}
          </div>
        )}

        {/* ==================================================== */}
        {/* Search Results Area                                  */}
        {/* ==================================================== */}

        {!loading && mode === "search" && response && (
          <section className="space-y-5 animate-fade-in-up">

            {/* Out of Scope Banner */}
            {isOutOfScope ? (
              <div className="mono-card rounded-2xl border-caution/40 bg-caution/5 p-6 text-caution animate-fade-in-up">

                <div className="flex items-center gap-2 font-bold text-sm">

                  <svg
                    className="h-5 w-5 text-caution"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z"
                    />
                  </svg>

                  <span>
                    {lang === "ar"
                      ? "السؤال خارج نطاق Eva AI"
                      : "Question Outside Scope"}
                  </span>

                </div>

                <p className="mt-2 text-xs leading-relaxed text-caution/90">
                  {response.scope_message}
                </p>

                <div className="mt-4 mono-inset rounded-xl p-4 text-xs text-ink-dim">

                  <p className="font-bold text-ink">
                    {lang === "ar"
                      ? "النطاق الحالي"
                      : "Current Scope"}
                  </p>

                  <p className="mt-1 leading-relaxed">
                    {lang === "ar"
                      ? "Eva AI متخصصة حاليًا في قصور الغدة الكظرية وتحديده وإدارته استنادًا إلى إرشادات NICE NG243."
                      : "Eva AI currently covers adrenal insufficiency, including its identification and management, based on the registered NICE NG243 guideline."}
                  </p>

                </div>

              </div>
            ) : (
              <>
                {/* Eva AI Toolbar */}
                <div className="mono-card flex flex-wrap items-center justify-between gap-4 rounded-2xl p-3.5 text-xs">

                  <div className="flex items-center gap-2.5 text-ink-dim">

                    <span className="mono-pill px-2.5 py-1 font-mono font-extrabold text-ink">
                      {response.result_count}{" "}
                      {t.resultCount}
                    </span>

                    <span>·</span>

                    <span className="font-semibold text-accent-bright">
                      {aboveFloorCount}{" "}
                      {t.aboveFloor}
                    </span>

                    <span>·</span>

                    <span className="font-mono text-accent-bright font-bold">
                      ⚡ {response.latency_ms} ms
                    </span>

                  </div>

                  {/* Filter Tabs */}
                  <div className="mono-inset flex items-center gap-1 rounded-xl p-1">

                    <FilterButton
                      active={filterMode === "all"}
                      onClick={() =>
                        setFilterMode("all")
                      }
                      label={`${t.filterAll} (${response.results.length})`}
                    />

                    <FilterButton
                      active={filterMode === "high"}
                      onClick={() =>
                        setFilterMode("high")
                      }
                      label={t.filterHigh}
                    />

                    {response.results.some(
                      (r) => r.below_floor
                    ) && (
                      <FilterButton
                        active={
                          filterMode === "floor"
                        }
                        onClick={() =>
                          setFilterMode("floor")
                        }
                        label={t.filterFloor}
                      />
                    )}

                  </div>

                </div>

                {/* No Evidence Banner */}
                {hasNoEvidence && (
                  <div className="mono-card rounded-2xl border-caution/40 bg-caution/5 p-5 text-caution">

                    <div className="flex items-center gap-2 font-bold text-sm">

                      <svg
                        className="h-5 w-5 text-caution"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0"
                        />
                      </svg>

                      <span>
                        {lang === "ar"
                          ? "لم يتم العثور على دليل قوي"
                          : "No Strong Evidence Found"}
                      </span>

                    </div>

                    <p className="mt-1.5 text-xs leading-relaxed text-caution/90">
                      {response.scope_message}
                    </p>

                  </div>
                )}

                {/* In Scope Status */}
                {isInScope && response.evidence_found && (
                  <div className="mono-inset rounded-xl px-4 py-3 text-xs text-ink-dim">

                    <div className="flex items-center gap-2">

                      <span className="h-2 w-2 rounded-full bg-accent-bright" />

                      <span>
                        {lang === "ar"
                          ? "تم العثور على دليل سريري ذي صلة."
                          : "Relevant clinical evidence found."}
                      </span>

                    </div>

                  </div>
                )}

                {/* Retrieved Chunks */}
                <div className="space-y-4">

                  {filteredResults.length > 0 ? (
                    filteredResults.map((result) => (
                      <ChunkCard
                        key={result.chunk.chunk_id}
                        result={result}
                      />
                    ))
                  ) : (
                    <div className="mono-inset rounded-2xl p-8 text-center text-xs text-ink-faint">
                      {t.noMatchFilter} ({filterMode}).
                    </div>
                  )}

                </div>
              </>
            )}

          </section>
        )}

        {/* ==================================================== */}
        {/* Generation Results Area                              */}
        {/* ==================================================== */}

        {!loading && mode === "generate" && genResponse && (
          <section className="space-y-5 animate-fade-in-up">
            <AnswerCard result={genResponse} />
          </section>
        )}

        {/* ==================================================== */}
        {/* Eva AI Empty State                                   */}
        {/* ==================================================== */}

        {!loading && !response && !genResponse && !error && (
          <div className="mono-card rounded-2xl p-10 text-center animate-fade-in-up">

            <div className="mono-button mx-auto flex h-16 w-16 items-center justify-center rounded-2xl text-accent-bright border border-accent-bright/20 shadow-md">

              <span className="font-brand-cursive text-3xl text-accent-bright drop-shadow">
                E
              </span>

              <span className="font-brand-serif text-sm font-bold text-accent-bright -ml-0.5">
                A
              </span>

            </div>

            <h2 className="mt-5 text-lg font-extrabold text-ink tracking-wide">

              <span className="font-brand-cursive text-2xl font-normal text-accent-bright me-1">
                Eva
              </span>

              <span className="font-brand-serif text-accent-bright me-2">
                AI
              </span>

              {t.inspectorReadyTitle}

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

      {/* ====================================================== */}
      {/* Sidebar                                                */}
      {/* ====================================================== */}

      <IndexStatus />

    </div>
  );
}

/* ============================================================ */
/* Filter Button                                                */
/* ============================================================ */

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

/* ============================================================ */
/* Feature Card                                                 */
/* ============================================================ */

function FeatureCard({
  icon,
  title,
  desc,
}: {
  icon: string;
  title: string;
  desc: string;
}) {
  return (
    <div className="mono-card-interactive rounded-xl p-4">

      <div className="text-2xl">
        {icon}
      </div>

      <h3 className="mt-2 text-xs font-bold text-ink">
        {title}
      </h3>

      <p className="mt-1 text-[11px] leading-relaxed text-ink-faint">
        {desc}
      </p>

    </div>
  );
}