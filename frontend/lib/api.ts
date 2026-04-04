const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

export type RatingValue =
  | "untrue"
  | "mostly_untrue"
  | "somewhat_true"
  | "true"
  | "unresolved"
  | "not_a_prediction";

export type SourceType = "substack" | "google_news" | "youtube" | "website" | "podcast" | "youtube_guest" | "podcast_guest" | "twitter" | "cnbc" | "fox_news" | "bloomberg";

export interface AnalystScore {
  total_predictions: number;
  judged_predictions: number;
  finalized_predictions: number;
  accuracy_score: number | null;
  weighted_accuracy_score: number | null;
  letter_grade: string | null;
  rating_breakdown: Record<string, number>;
}

export interface Analyst {
  id: number;
  name: string;
  slug: string;
  bio: string | null;
  substack_url: string | null;
  youtube_channel_id: string | null;
  website_url: string | null;
  podcast_rss_url: string | null;
  twitter_handle: string | null;
  profile_image_url: string | null;
  narrative_summary: string | null;
  summary_updated_at: string | null;
  is_active: boolean;
  is_public: boolean;
  created_at: string;
  score: AnalystScore | null;
}

export interface Statement {
  id: number;
  analyst_id: number;
  source_type: SourceType;
  source_url: string;
  source_title: string | null;
  content: string;
  published_at: string | null;
  collected_at: string;
  is_processed: boolean;
}

export interface PredictionOutcome {
  id: number;
  prediction_id: number;
  evidence_text: string | null;
  evidence_urls: string | null;
  llm_rating: RatingValue | null;
  llm_reasoning: string | null;
  human_rating: RatingValue | null;
  human_notes: string | null;
  is_finalized: boolean;
  judged_at: string | null;
  reviewed_at: string | null;
}

export interface Prediction {
  id: number;
  statement_id: number;
  analyst_id: number;
  prediction_text: string;
  predicted_event: string | null;
  predicted_timeframe: string | null;
  confidence_language: string | null;
  extracted_at: string;
  outcome: PredictionOutcome | null;
  statement: Statement | null;
}

export interface AnalystDetail extends Analyst {
  predictions: Prediction[];
}

export interface ReviewQueueItem {
  outcome_id: number;
  prediction_id: number;
  prediction_text: string;
  predicted_event: string | null;
  predicted_timeframe: string | null;
  confidence_language: string | null;
  statement_title: string | null;
  statement_url: string;
  statement_source_type: SourceType;
  published_at: string | null;
  analyst_name: string;
  analyst_slug: string;
  llm_rating: RatingValue | null;
  llm_reasoning: string | null;
  evidence_text: string | null;
  evidence_urls: string | null;
  judged_at: string | null;
}

export interface CollectResult {
  analyst_id: number;
  substack_new: number;
  google_news_new: number;
  youtube_new: number;
  podcast_new: number;
  youtube_guest_new: number;
  podcast_guest_new: number;
  twitter_new: number;
  cnbc_new: number;
  total_new: number;
  total_statements: number;
}

export interface ProcessResult {
  analyst_id: number;
  statements_processed: number;
  statements_skipped: number;
  predictions_extracted: number;
}

export interface JudgeResult {
  analyst_id: number;
  predictions_judged: number;
}

export interface AnalystCreate {
  name: string;
  bio?: string;
  substack_url?: string;
  youtube_channel_id?: string;
  website_url?: string;
  podcast_rss_url?: string;
  twitter_handle?: string;
  profile_image_url?: string;
}

export interface OutcomeUpdate {
  human_rating: RatingValue;
  human_notes?: string;
}

// ── Fetch helpers ─────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Analysts ──────────────────────────────────────────────────────────────────

export async function fetchAnalysts(cacheMode?: RequestCache, admin = false): Promise<Analyst[]> {
  const url = admin ? "/api/analysts?admin=true" : "/api/analysts";
  return apiFetch<Analyst[]>(url, { cache: cacheMode ?? "no-store" });
}

export async function fetchAnalyst(slug: string, cacheMode?: RequestCache): Promise<AnalystDetail> {
  return apiFetch<AnalystDetail>(`/api/analysts/${slug}`, { cache: cacheMode ?? "no-store" });
}

export async function createAnalyst(data: AnalystCreate): Promise<Analyst> {
  return apiFetch<Analyst>("/api/analysts", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export interface AnalystLookup {
  bio: string | null;
  substack_url: string | null;
  youtube_channel_id: string | null;
  website_url: string | null;
  podcast_rss_url: string | null;
  profile_image_url: string | null;
}

export interface AnalystUpdate {
  name?: string;
  bio?: string;
  substack_url?: string;
  youtube_channel_id?: string;
  website_url?: string;
  podcast_rss_url?: string;
  twitter_handle?: string;
  profile_image_url?: string;
  is_public?: boolean;
}

export async function lookupAnalyst(name: string): Promise<AnalystLookup> {
  return apiFetch<AnalystLookup>("/api/analysts/lookup", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function collectData(analystId: number): Promise<CollectResult> {
  return apiFetch<CollectResult>(`/api/analysts/${analystId}/collect`, {
    method: "POST",
  });
}

export async function processStatements(analystId: number): Promise<ProcessResult> {
  return apiFetch<ProcessResult>(`/api/analysts/${analystId}/process`, {
    method: "POST",
  });
}

export async function judgeAnalyst(analystId: number): Promise<JudgeResult> {
  return apiFetch<JudgeResult>(`/api/analysts/${analystId}/judge`, {
    method: "POST",
  });
}

export async function regenerateSummary(analystId: number): Promise<{ summary: string }> {
  return apiFetch<{ summary: string }>(`/api/analysts/${analystId}/summarize`, {
    method: "POST",
  });
}

export async function updateAnalyst(analystId: number, data: AnalystUpdate): Promise<Analyst> {
  return apiFetch<Analyst>(`/api/analysts/${analystId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function fetchPhoto(analystId: number): Promise<Analyst> {
  return apiFetch<Analyst>(`/api/analysts/${analystId}/fetch-photo`, {
    method: "POST",
  });
}

export async function fetchAnalystScore(analystId: number): Promise<AnalystScore> {
  return apiFetch<AnalystScore>(`/api/analysts/${analystId}/score`, {
    cache: "no-store",
  });
}

// ── Review ────────────────────────────────────────────────────────────────────

export async function fetchReviewQueue(): Promise<ReviewQueueItem[]> {
  return apiFetch<ReviewQueueItem[]>("/api/review/queue", { cache: "no-store" });
}

export async function finalizeOutcome(
  outcomeId: number,
  data: OutcomeUpdate
): Promise<PredictionOutcome> {
  return apiFetch<PredictionOutcome>(`/api/review/${outcomeId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function ratePrediction(
  predictionId: number,
  data: OutcomeUpdate
): Promise<PredictionOutcome> {
  return apiFetch<PredictionOutcome>(`/api/review/prediction/${predictionId}`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Bulk Import ───────────────────────────────────────────────────────────────

export interface BulkImportRequest {
  analyst_id: number;
  urls: string[];
  source_type?: string;
}

export interface BulkImportResult {
  total: number;
  imported: number;
  skipped: number;
  failed: string[];
}

export async function bulkImport(data: BulkImportRequest): Promise<BulkImportResult> {
  return apiFetch<BulkImportResult>("/api/bulk-import", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Predictions ───────────────────────────────────────────────────────────────

export async function fetchPrediction(id: number): Promise<Prediction> {
  return apiFetch<Prediction>(`/api/predictions/${id}`, { cache: "no-store" });
}
