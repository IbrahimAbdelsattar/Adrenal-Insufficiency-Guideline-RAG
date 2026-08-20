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
  dense_score?: number;
  bm25_score?: number;
  rerank_score?: number;
  retriever_mode?: string;
}

export type ScopeStatus = "in_scope" | "no_evidence" | "out_of_scope";

export interface SearchResponse {
  query: string;
  results: RetrievalResult[];
  result_count: number;
  evidence_found: boolean;
  scope_status: ScopeStatus;
  scope_message: string;
  embedding_model: string;
  latency_ms: number;
  disclaimer: string;
}

export interface Citation {
  source_id: string;
  document_name: string;
  section_title: string;
  section_number: string;
  page_number: number;
  source_url: string;
  recommendation_ids?: string;
  excerpt?: string;
  text?: string;
  score?: number;
  absolute_relevance?: number;
  // "source_marker": the model wrote [Source N] directly against this claim
  // (an explicit claim citation). "recommendation_id": the model cited the
  // guideline's own numbering (e.g. [1.8.6]); resolved to an exact chunk,
  // but never validated against a specific sentence -- an indirect match.
  resolved_by?: "source_marker" | "recommendation_id";
  below_floor?: boolean;
  publication_year?: number;
  document_type?: string;
  requires_caution?: boolean;
  retrieved_at?: string;
}

export type GroundingStatus = "verified" | "failed" | "abstained";

export type InputRiskTier =
  | "emergency_critical"
  | "sick_day_stress"
  | "pediatric_specialist"
  | "steroid_withdrawal"
  | "adversarial_security"
  | "out_of_scope"
  | "routine_clinical";

export interface InputRiskAssessment {
  tier: InputRiskTier;
  is_emergency: boolean;
  risk_score: number;
  detected_risk_factors: string[];
  recommended_triage_action: string;
  safety_banner: string;
}

export interface GenerateResponse {
  query: string;
  answer: string;
  citations: Citation[];
  evidence_found: boolean;
  disclaimer: string;
  model: string;
  latency_ms: number;
  cache_hit?: boolean;
  grounding_status?: GroundingStatus;
  clarifying_questions?: string[];
  risk_assessment?: InputRiskAssessment;
}

export interface StreamMeta {
  query: string;
  model: string;
  evidence_found: boolean;
  cache_hit: boolean;
  clarifying_questions?: string[];
  risk_assessment?: InputRiskAssessment;
}

export interface StreamDone {
  citations: Citation[];
  latency_ms: number;
  disclaimer: string;
  grounding_status?: GroundingStatus;
  risk_assessment?: InputRiskAssessment;
}

export interface StreamCallbacks {
  onMeta?: (meta: StreamMeta) => void;
  onToken: (text: string) => void;
  onDone: (done: StreamDone) => void;
  onError?: (detail: string) => void;
}

export interface ChatHistoryMessage {
  role: "user" | "assistant";
  content: string;
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

/**
 * Generate an answer grounded in clinical guidelines.
 */
export function generate(
  query: string,
  topK: number,
  history: ChatHistoryMessage[] = [],
): Promise<GenerateResponse> {
  return request<GenerateResponse>("/api/generate", {
    method: "POST",
    body: JSON.stringify({ query, top_k: topK, history }),
  });
}

/**
 * Generate an answer as a server-sent event stream so tokens
 * render as they are produced (low perceived latency).
 */
export async function generateStream(
  query: string,
  topK: number,
  callbacks: StreamCallbacks,
  history: ChatHistoryMessage[] = [],
): Promise<void> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE}/api/generate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK, history }),
    });
  } catch {
    throw new ApiError(
      "Cannot reach the backend. Is it running on port 8010?",
      0,
    );
  }

  if (!response.ok || !response.body) {
    let detail = `Request failed (${response.status}).`;

    try {
      const body = await response.json();

      if (typeof body?.detail === "string") {
        detail = body.detail;
      }
    } catch {
      /* Keep fallback message */
    }

    throw new ApiError(detail, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let separator: number;

    while ((separator = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);

      let event = "message";
      const dataLines: string[] = [];

      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) {
          event = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }

      if (dataLines.length === 0) {
        continue;
      }

      try {
        const data = JSON.parse(dataLines.join("\n"));

        if (event === "meta") {
          callbacks.onMeta?.(data as StreamMeta);
        } else if (event === "token") {
          callbacks.onToken(data.text ?? "");
        } else if (event === "done") {
          callbacks.onDone(data as StreamDone);
        } else if (event === "error") {
          callbacks.onError?.(data.detail ?? "Generation failed.");
        }
      } catch {
        /* Ignore malformed frames */
      }
    }
  }
}

/**
 * Get service health and active retriever type.
 */
export function getHealth(): Promise<{ retriever_type?: string; status?: string }> {
  return request<{ retriever_type?: string; status?: string }>("/api/health");
}
