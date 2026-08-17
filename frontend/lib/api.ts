/**
 * Typed client for the FastAPI backend.
 * Shapes mirror the FastAPI response models.
 */

export interface Chunk {
  chunk_id: string;
  text: string;
  document_name: string;
  doc_id: string;
  source_url: string;
  document_type: string;
  publication_year: number;
  requires_caution: boolean;
  page_number: number;
  section_title: string;
  section_number: string;
  subsection_title: string;
  recommendation_ids: string;
  token_count: number;
  is_oversized: boolean;
}

export interface RetrievalResult {
  chunk: Chunk;
  score: number;
  rank: number;
  below_floor: boolean;
}

/**
 * Scope classification returned by the backend.
 *
 * in_scope:
 *   The question is related to the current clinical topic
 *   and relevant evidence was found.
 *
 * no_evidence:
 *   The question appears related to the topic, but the
 *   retrieved evidence is not strong enough.
 *
 * out_of_scope:
 *   The question is outside the current scope of Eva AI.
 */
export type ScopeStatus =
  | "in_scope"
  | "no_evidence"
  | "out_of_scope";

export interface SearchResponse {
  query: string;

  /**
   * Retrieved chunks.
   *
   * For out_of_scope queries this will be an empty array,
   * because unrelated evidence should not be shown to the user.
   */
  results: RetrievalResult[];

  result_count: number;

  /**
   * True only when strong evidence was found.
   */
  evidence_found: boolean;

  /**
   * Indicates whether the query is inside or outside
   * the current knowledge scope.
   */
  scope_status: ScopeStatus;

  /**
   * Human-readable explanation of the scope/evidence state.
   */
  scope_message: string;

  embedding_model: string;
  latency_ms: number;
  disclaimer: string;
}

export interface PerDocumentStats {
  doc_id: string;
  pages_processed: number;
  pages_empty: number;
  chunk_count: number;
}

export interface IndexManifest {
  built_at: string;
  embedding_model: string;
  embedding_dimensions: number;
  chunk_target_tokens: number;
  chunk_min_tokens: number;
  chunk_max_tokens: number;
  document_count: number;
  chunk_count: number;
  oversized_chunk_count: number;
  per_document: PerDocumentStats[];
}

export interface SourceDocument {
  doc_id: string;
  document_name: string;
  publisher: string;
  publication_year: number;
  source_url: string;
  document_type: string;
  credibility_note: string;
  license_note: string;
  requires_caution: boolean;
}

/**
 * Thrown with the backend's own `detail` message
 * so the UI can show it verbatim.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Base URL for API calls.
 *
 * Empty (the default) means same-origin, which is what local
 * development and the single-process production image both want.
 *
 * In the split VPS deployment it is set to the backend's own
 * domain so the browser talks to FastAPI directly.
 */
const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? ""
).replace(/\/$/, "");

/**
 * Generic API request helper.
 */
async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(
      `${API_BASE}${path}`,
      {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(init?.headers ?? {}),
        },
      },
    );
  } catch {
    throw new ApiError(
      "Cannot reach the backend. Is it running on port 8010?",
      0,
    );
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;

    try {
      const body = await response.json();

      if (
        typeof body?.detail === "string"
      ) {
        detail = body.detail;
      }
    } catch {
      /* Keep fallback message */
    }

    throw new ApiError(
      detail,
      response.status,
    );
  }

  return response.json() as Promise<T>;
}

/**
 * Search the clinical knowledge base.
 *
 * The backend is responsible for:
 * - semantic retrieval
 * - evidence threshold
 * - scope detection
 * - filtering out unrelated results
 */
export function search(
  query: string,
  topK: number,
): Promise<SearchResponse> {
  return request<SearchResponse>(
    "/api/search",
    {
      method: "POST",
      body: JSON.stringify({
        query,
        top_k: topK,
      }),
    },
  );
}

/**
 * Get information about the current vector index.
 */
export function getIndexStatus(): Promise<IndexManifest> {
  return request<IndexManifest>(
    "/api/index",
  );
}

/**
 * Get registered clinical sources.
 */
export function getSources(): Promise<{
  sources: SourceDocument[];
}> {
  return request<{
    sources: SourceDocument[];
  }>("/api/sources");
}