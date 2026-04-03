"use client";

import { useState, useEffect } from "react";
import type { Prediction, RatingValue, PredictionOutcome } from "@/lib/api";
import { ratePrediction, finalizeOutcome } from "@/lib/api";
import RatingBadge from "./RatingBadge";

interface PredictionCardProps {
  prediction: Prediction;
}

const SOURCE_LABELS: Record<string, string> = {
  substack: "Substack",
  google_news: "Google News",
  youtube: "YouTube",
  website: "Website",
  podcast: "Podcast",
  youtube_guest: "YouTube (Guest)",
  podcast_guest: "Podcast (Guest)",
  twitter: "Twitter/X",
  cnbc: "CNBC Transcript",
  fox_news: "Fox News",
  bloomberg: "Bloomberg",
};

const RATING_OPTIONS: { value: RatingValue; label: string; color: string }[] = [
  { value: "true", label: "True", color: "bg-green-100 text-green-800 hover:bg-green-200 border-green-300" },
  { value: "somewhat_true", label: "Somewhat True", color: "bg-yellow-100 text-yellow-800 hover:bg-yellow-200 border-yellow-300" },
  { value: "mostly_untrue", label: "Mostly Untrue", color: "bg-orange-100 text-orange-800 hover:bg-orange-200 border-orange-300" },
  { value: "untrue", label: "Untrue", color: "bg-red-100 text-red-800 hover:bg-red-200 border-red-300" },
  { value: "unresolved", label: "Unresolved", color: "bg-gray-100 text-gray-700 hover:bg-gray-200 border-gray-300" },
  { value: "not_a_prediction", label: "Not a Prediction", color: "bg-purple-100 text-purple-700 hover:bg-purple-200 border-purple-300" },
];

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function PredictionCard({ prediction }: PredictionCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [outcome, setOutcome] = useState<typeof prediction.outcome>(prediction.outcome);
  const [rating, setRating] = useState(false);
  const statement = prediction.statement;

  useEffect(() => {
    setIsAdmin(sessionStorage.getItem("admin_authed") === "true");
  }, []);

  const displayRating: RatingValue | null = outcome?.human_rating ?? outcome?.llm_rating ?? null;
  const isPending = !!(outcome && !outcome.is_finalized && !outcome.human_rating && outcome.llm_rating);
  const isFinalized = !!outcome?.is_finalized;

  async function handleRate(value: RatingValue) {
    setRating(true);
    try {
      let updated: typeof outcome;
      if (outcome?.id) {
        updated = await finalizeOutcome(outcome.id, { human_rating: value });
      } else {
        updated = await ratePrediction(prediction.id, { human_rating: value });
      }
      setOutcome(updated);
    } catch (err) {
      console.error("Rating failed", err);
    } finally {
      setRating(false);
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <blockquote className="flex-1 text-sm text-gray-800 italic leading-relaxed">
          &ldquo;{prediction.prediction_text}&rdquo;
        </blockquote>
        <div className="shrink-0">
          <RatingBadge rating={displayRating} isPending={isPending} />
        </div>
      </div>

      {/* Metadata */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
        {prediction.predicted_event && (
          <span className="font-medium text-gray-700">{prediction.predicted_event}</span>
        )}
        {prediction.predicted_timeframe && (
          <span>Timeframe: {prediction.predicted_timeframe}</span>
        )}
        {prediction.confidence_language && (
          <span className="italic">&ldquo;{prediction.confidence_language}&rdquo;</span>
        )}
      </div>

      {/* Source info */}
      {statement && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-400">
          <span className="rounded bg-gray-100 px-1.5 py-0.5 font-medium uppercase tracking-wide text-gray-500">
            {SOURCE_LABELS[statement.source_type] ?? statement.source_type}
          </span>
          <a
            href={statement.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="max-w-xs truncate text-blue-500 hover:underline"
          >
            {statement.source_title || statement.source_url}
          </a>
          {statement.published_at && (
            <span>{formatDate(statement.published_at)}</span>
          )}
        </div>
      )}

      {/* Expandable reasoning */}
      {outcome?.llm_reasoning && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800"
          >
            <svg
              className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-90" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            {expanded ? "Hide" : "Show"} reasoning
          </button>

          {expanded && (
            <div className="mt-2 rounded-md bg-gray-50 p-3 text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">
              {outcome.llm_reasoning}
              {outcome.human_notes && (
                <div className="mt-2 border-t border-gray-200 pt-2">
                  <span className="font-semibold text-gray-700">Reviewer notes: </span>
                  {outcome.human_notes}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Inline rating — admin only, unfinalized predictions */}
      {isAdmin && !isFinalized && (
        <div className="mt-3 border-t border-gray-100 pt-3">
          <p className="mb-1.5 text-xs text-gray-400">Rate this prediction:</p>
          <div className="flex flex-wrap gap-1.5">
            {RATING_OPTIONS.map(({ value, label, color }) => (
              <button
                key={value}
                onClick={() => handleRate(value)}
                disabled={rating}
                className={`rounded border px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${color}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Show edit button for already-finalized predictions when admin */}
      {isAdmin && isFinalized && (
        <div className="mt-2 flex justify-end">
          <button
            onClick={() => setOutcome((o) => o ? { ...o, is_finalized: false } : o)}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Edit rating
          </button>
        </div>
      )}
    </div>
  );
}
