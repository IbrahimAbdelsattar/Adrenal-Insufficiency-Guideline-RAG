/**
 * Typed client for the FastAPI backend.
 * Shapes mirror specs/001-clinical-rag-ingestion/contracts/search-api.yaml.
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

export interface SearchResponse {
  query: string;
  results: RetrievalResult[];
  result_count: number;
  evidence_found: boolean;
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

/** Thrown with the backend's own `detail` message so the UI can show it verbatim. */
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
 * Empty (the default) means same-origin, which is what local development and
 * the single-process production image both want.
 *
 * In the split VPS deployment it is set to the backend's own domain so the
 * browser talks to FastAPI directly. Routing POSTs through the Next rewrite
 * behind Traefik makes Next reject them with `400 Invalid host header`, so the
 * proxy is bypassed rather than worked around. CORS is granted to this origin
 * by the backend's ALLOWED_ORIGIN setting.
 *
 * NEXT_PUBLIC_* is inlined at build time, so this must be a Docker build arg.
 */
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
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
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the fallback message */
    }
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

export function search(query: string, topK: number): Promise<SearchResponse> {
  return request<SearchResponse>("/api/search", {
    method: "POST",
    body: JSON.stringify({ query, top_k: topK }),
  });
}

export function getIndexStatus(): Promise<IndexManifest> {
  return request<IndexManifest>("/api/index");
}

export function getSources(): Promise<{ sources: SourceDocument[] }> {
  return request<{ sources: SourceDocument[] }>("/api/sources");
}
