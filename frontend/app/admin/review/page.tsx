"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  fetchReviewQueue,
  finalizeOutcome,
  type ReviewQueueItem,
  type RatingValue,
} from "@/lib/api";

const RATING_OPTIONS: { value: RatingValue; label: string }[] = [
  { value: "true", label: "True" },
  { value: "somewhat_true", label: "Somewhat True" },
  { value: "mostly_untrue", label: "Mostly Untrue" },
  { value: "untrue", label: "Untrue" },
  { value: "unresolved", label: "Unresolved" },
  { value: "not_a_prediction", label: "Not a Prediction" },
];

const LLM_RATING_LABELS: Record<string, string> = {
  true: "True",
  somewhat_true: "Somewhat True",
  mostly_untrue: "Mostly Untrue",
  untrue: "Untrue",
  unresolved: "Unresolved",
  not_a_prediction: "Not a Prediction",
};

const LLM_RATING_COLORS: Record<string, string> = {
  true: "text-green-700 bg-green-50 border-green-200",
  somewhat_true: "text-yellow-700 bg-yellow-50 border-yellow-200",
  mostly_untrue: "text-orange-700 bg-orange-50 border-orange-200",
  untrue: "text-red-700 bg-red-50 border-red-200",
  unresolved: "text-gray-600 bg-gray-50 border-gray-200",
  not_a_prediction: "text-purple-700 bg-purple-50 border-purple-200",
};

interface ItemState {
  rating: RatingValue | "";
  notes: string;
  submitting: boolean;
  done: boolean;
  error: string | null;
}

function formatDate(s: string | null) {
  if (!s) return "";
  return new Date(s).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export default function ReviewQueuePage() {
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [itemStates, setItemStates] = useState<Record<number, ItemState>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const q = await fetchReviewQueue();
      setItems(q);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load review queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function getState(outcomeId: number): ItemState {
    return itemStates[outcomeId] ?? { rating: "", notes: "", submitting: false, done: false, error: null };
  }

  function updateState(outcomeId: number, patch: Partial<ItemState>) {
    setItemStates((prev) => ({
      ...prev,
      [outcomeId]: { ...getState(outcomeId), ...patch },
    }));
  }

  async function handleFinalize(item: ReviewQueueItem) {
    const state = getState(item.outcome_id);
    if (!state.rating) return;

    updateState(item.outcome_id, { submitting: true, error: null });
    try {
      await finalizeOutcome(item.outcome_id, {
        human_rating: state.rating as RatingValue,
        human_notes: state.notes || undefined,
      });
      updateState(item.outcome_id, { submitting: false, done: true });
    } catch (err) {
      updateState(item.outcome_id, {
        submitting: false,
        error: err instanceof Error ? err.message : "Failed to finalize",
      });
    }
  }

  const pendingItems = items.filter((item) => !getState(item.outcome_id).done);
  const doneCount = items.length - pendingItems.length;

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <Link href="/admin" className="mb-2 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Admin Dashboard
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
          <p className="mt-1 text-sm text-gray-500">
            {loading ? "Loading..." : `${pendingItems.length} predictions awaiting human review${doneCount > 0 ? ` · ${doneCount} finalized this session` : ""}`}
          </p>
        </div>
        <button
          onClick={load}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-center py-12 text-gray-400">Loading review queue...</div>
      )}

      {!loading && pendingItems.length === 0 && (
        <div className="rounded-xl border-2 border-dashed border-gray-200 p-12 text-center">
          <div className="text-4xl mb-3">✓</div>
          <p className="text-gray-500">
            {items.length === 0
              ? "The review queue is empty. Run prediction judging first."
              : "All predictions have been reviewed!"}
          </p>
        </div>
      )}

      <div className="space-y-6">
        {pendingItems.map((item) => {
          const state = getState(item.outcome_id);
          const llmRatingColor = item.llm_rating ? LLM_RATING_COLORS[item.llm_rating] : "text-gray-500 bg-gray-50 border-gray-200";

          return (
            <div key={item.outcome_id} className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
              {/* Header */}
              <div className="border-b border-gray-100 bg-gray-50 px-5 py-3 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Link
                    href={`/analysts/${item.analyst_slug}`}
                    className="font-medium text-gray-900 hover:text-blue-600"
                  >
                    {item.analyst_name}
                  </Link>
                  <span>·</span>
                  <span className="rounded bg-gray-200 px-1.5 py-0.5 text-xs uppercase tracking-wide">
                    {item.statement_source_type}
                  </span>
                  {item.published_at && (
                    <>
                      <span>·</span>
                      <span>{formatDate(item.published_at)}</span>
                    </>
                  )}
                </div>
              </div>

              <div className="p-5 space-y-4">
                {/* Prediction */}
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-gray-400 mb-1">Prediction</p>
                  <blockquote className="text-gray-900 italic leading-relaxed border-l-4 border-blue-200 pl-3">
                    &ldquo;{item.prediction_text}&rdquo;
                  </blockquote>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-500">
                    {item.predicted_event && (
                      <span><strong>Event:</strong> {item.predicted_event}</span>
                    )}
                    {item.predicted_timeframe && (
                      <span><strong>Timeframe:</strong> {item.predicted_timeframe}</span>
                    )}
                    {item.confidence_language && (
                      <span><strong>Confidence language:</strong> &ldquo;{item.confidence_language}&rdquo;</span>
                    )}
                  </div>
                </div>

                {/* Source */}
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-gray-400 mb-1">Source</p>
                  <a
                    href={item.statement_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:underline"
                  >
                    {item.statement_title || item.statement_url}
                  </a>
                </div>

                {/* Evidence */}
                {item.evidence_text && item.evidence_text !== "No relevant news articles found." && (
                  <details className="group">
                    <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-gray-400 hover:text-gray-600">
                      Evidence ({item.evidence_text.split("\n-").length - 1 || 1} sources)
                    </summary>
                    <div className="mt-2 rounded-lg bg-gray-50 border border-gray-200 p-3 text-xs text-gray-600 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                      {item.evidence_text}
                    </div>
                  </details>
                )}

                {/* Human Review Form */}
                <div className="border-t border-gray-100 pt-4">
                  {/* LLM suggestion — shown directly above the rating picker */}
                  {item.llm_rating && (
                    <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50 p-3">
                      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-blue-400">
                        AI Suggestion
                      </p>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${llmRatingColor}`}>
                          {LLM_RATING_LABELS[item.llm_rating]}
                        </span>
                      </div>
                      {item.llm_reasoning && (
                        <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                          {item.llm_reasoning}
                        </p>
                      )}
                    </div>
                  )}
                  <p className="mb-3 text-sm font-semibold text-gray-700">Your Rating</p>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                    <div className="flex-1 space-y-3">
                      <select
                        value={state.rating}
                        onChange={(e) => updateState(item.outcome_id, { rating: e.target.value as RatingValue | "" })}
                        className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        <option value="">-- Select a rating --</option>
                        {RATING_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                      <textarea
                        placeholder="Optional notes (context, sources, reasoning...)"
                        value={state.notes}
                        onChange={(e) => updateState(item.outcome_id, { notes: e.target.value })}
                        rows={2}
                        className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    <button
                      onClick={() => handleFinalize(item)}
                      disabled={!state.rating || state.submitting}
                      className="shrink-0 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      {state.submitting ? "Saving..." : "Finalize"}
                    </button>
                  </div>
                  {state.error && (
                    <p className="mt-2 text-xs text-red-600">{state.error}</p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
