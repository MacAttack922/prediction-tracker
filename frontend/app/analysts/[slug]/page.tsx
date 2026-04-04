import { notFound } from "next/navigation";
import type { Metadata } from "next";
import Link from "next/link";
import { fetchAnalyst } from "@/lib/api";
import PredictionCard from "@/components/PredictionCard";
import type { Prediction } from "@/lib/api";

export const dynamic = "force-dynamic";

interface Props {
  params: { slug: string };
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

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  try {
    const analyst = await fetchAnalyst(params.slug, "no-store");
    const score = analyst.score;
    const scoreStr = score?.accuracy_score != null
      ? `${score.accuracy_score}% accuracy`
      : "No score yet";
    const gradeStr = score?.letter_grade ? ` · Grade ${score.letter_grade}` : "";
    const description = analyst.bio
      ? `${analyst.bio} — ${scoreStr}${gradeStr} on GuruBuster`
      : `${scoreStr}${gradeStr} — Track ${analyst.name}'s prediction record on GuruBuster`;

    return {
      title: `${analyst.name} — GuruBuster`,
      description,
      openGraph: {
        title: `${analyst.name} on GuruBuster`,
        description,
        ...(analyst.profile_image_url && { images: [analyst.profile_image_url] }),
      },
      twitter: {
        card: "summary",
        title: `${analyst.name} on GuruBuster`,
        description,
        ...(analyst.profile_image_url && { images: [analyst.profile_image_url] }),
      },
    };
  } catch {
    return { title: "Analyst — GuruBuster" };
  }
}

function getGradeColors(grade: string | null) {
  if (!grade) return { bg: "bg-gray-100", text: "text-gray-500", border: "border-gray-200" };
  if (grade.startsWith("A")) return { bg: "bg-green-100", text: "text-green-700", border: "border-green-300" };
  if (grade.startsWith("B")) return { bg: "bg-blue-100", text: "text-blue-700", border: "border-blue-300" };
  if (grade.startsWith("C")) return { bg: "bg-yellow-100", text: "text-yellow-700", border: "border-yellow-300" };
  if (grade.startsWith("D")) return { bg: "bg-orange-100", text: "text-orange-700", border: "border-orange-300" };
  return { bg: "bg-red-100", text: "text-red-700", border: "border-red-300" };
}

function getScoreBarColor(score: number): string {
  if (score >= 75) return "bg-green-500";
  if (score >= 50) return "bg-yellow-500";
  if (score >= 25) return "bg-orange-500";
  return "bg-red-500";
}

function getScoreTextColor(score: number): string {
  if (score >= 75) return "text-green-600";
  if (score >= 50) return "text-yellow-600";
  if (score >= 25) return "text-orange-600";
  return "text-red-600";
}

export default async function AnalystProfilePage({ params }: Props) {
  let analyst;
  try {
    analyst = await fetchAnalyst(params.slug, "no-store");
  } catch {
    notFound();
  }

  const score = analyst.score;
  const predictions = analyst.predictions ?? [];
  const hasScore = score?.accuracy_score != null;
  const grade = score?.letter_grade ?? null;
  const gradeColors = getGradeColors(grade);

  // Group by source type
  const bySource: Record<string, Prediction[]> = {};
  for (const p of predictions) {
    const key = p.statement?.source_type ?? "unknown";
    if (!bySource[key]) bySource[key] = [];
    bySource[key].push(p);
  }

  // Notable calls
  const calledIt = predictions.filter(
    (p) => p.outcome?.is_finalized && p.outcome?.human_rating === "true"
  );
  const gotItWrong = predictions.filter(
    (p) => p.outcome?.is_finalized && p.outcome?.human_rating === "untrue"
  );

  // Rating breakdown
  const breakdown = score?.rating_breakdown ?? {};
  const ratingRows = [
    { key: "true", label: "True", barColor: "bg-green-500" },
    { key: "somewhat_true", label: "Somewhat True", barColor: "bg-yellow-400" },
    { key: "mostly_untrue", label: "Mostly Untrue", barColor: "bg-orange-400" },
    { key: "untrue", label: "Untrue", barColor: "bg-red-500" },
    { key: "unresolved", label: "Unresolved", barColor: "bg-gray-400" },
  ];

  return (
    <div className="mx-auto max-w-3xl">
      {/* Back */}
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        All Analysts
      </Link>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
        {/* Top band */}
        <div className="bg-gradient-to-r from-gray-50 to-gray-100 px-6 pt-8 pb-6">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
            {/* Photo */}
            <div className="shrink-0">
              {analyst.profile_image_url ? (
                <img
                  src={analyst.profile_image_url}
                  alt={analyst.name}
                  className="h-24 w-24 rounded-full object-cover border-4 border-white shadow-md"
                />
              ) : (
                <div className="h-24 w-24 rounded-full bg-gray-200 border-4 border-white shadow-md flex items-center justify-center text-3xl font-bold text-gray-400">
                  {analyst.name.charAt(0)}
                </div>
              )}
            </div>

            {/* Name + bio + links */}
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold text-gray-900 leading-tight">{analyst.name}</h1>
              {analyst.bio && (
                <p className="mt-1.5 text-sm text-gray-600 leading-relaxed">{analyst.bio}</p>
              )}
              {/* Source links */}
              <div className="mt-3 flex flex-wrap gap-2">
                {analyst.substack_url && (
                  <a href={analyst.substack_url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-200 transition-colors">
                    Substack
                  </a>
                )}
                {analyst.youtube_channel_id && (
                  <a href={`https://www.youtube.com/channel/${analyst.youtube_channel_id}`}
                    target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-800 hover:bg-red-200 transition-colors">
                    YouTube
                  </a>
                )}
                {analyst.website_url && (
                  <a href={analyst.website_url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-800 hover:bg-blue-200 transition-colors">
                    Website
                  </a>
                )}
                {analyst.twitter_handle && (
                  <a href={`https://twitter.com/${analyst.twitter_handle}`}
                    target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-800 hover:bg-sky-200 transition-colors">
                    Twitter/X
                  </a>
                )}
              </div>
            </div>

            {/* Grade badge */}
            {grade && (
              <div className={`shrink-0 flex flex-col items-center justify-center rounded-xl border-2 px-4 py-3 ${gradeColors.bg} ${gradeColors.border}`}>
                <span className={`text-4xl font-black ${gradeColors.text}`}>{grade}</span>
                <span className="mt-0.5 text-xs font-medium text-gray-500">Grade</span>
              </div>
            )}
          </div>
        </div>

        {/* Score bar */}
        <div className="px-6 py-5 border-t border-gray-100">
          <div className="flex items-end justify-between mb-2">
            <div className="flex items-baseline gap-2">
              {hasScore ? (
                <>
                  <span className={`text-3xl font-bold ${getScoreTextColor(score!.accuracy_score!)}`}>
                    {score!.accuracy_score}%
                  </span>
                  <span className="text-sm text-gray-500">accuracy</span>
                  {score?.weighted_accuracy_score != null && score.weighted_accuracy_score !== score.accuracy_score && (
                    <span className="text-xs text-gray-400">· {score.weighted_accuracy_score}% lead-time weighted</span>
                  )}
                </>
              ) : (
                <span className="text-xl font-semibold text-gray-400">No score yet</span>
              )}
            </div>
            <span className="text-xs text-gray-400">
              {score?.finalized_predictions ?? 0} of {score?.total_predictions ?? 0} predictions rated
            </span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded-full bg-gray-200">
            {hasScore && (
              <div
                className={`h-full rounded-full transition-all duration-700 ${getScoreBarColor(score!.accuracy_score!)}`}
                style={{ width: `${score!.accuracy_score}%` }}
              />
            )}
          </div>
          {!hasScore && (
            <p className="mt-2 text-xs text-gray-400">Predictions are tracked but none have been reviewed yet.</p>
          )}
        </div>

        {/* Rating breakdown */}
        {score && score.finalized_predictions > 0 && (
          <div className="px-6 pb-5 border-t border-gray-100">
            <p className="mb-3 mt-4 text-xs font-semibold uppercase tracking-wider text-gray-400">Rating Breakdown</p>
            <div className="grid grid-cols-5 gap-2 text-center">
              {ratingRows.map(({ key, label, barColor }) => (
                <div key={key} className="flex flex-col items-center gap-1">
                  <span className="text-xl font-bold text-gray-800">{breakdown[key] ?? 0}</span>
                  <div className={`h-1.5 w-full rounded-full ${barColor} opacity-80`} />
                  <span className="text-xs text-gray-500 leading-tight">{label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Narrative Summary ─────────────────────────────────────────────── */}
      {analyst.narrative_summary && (
        <div className="mt-6 rounded-xl border border-blue-100 bg-blue-50 px-6 py-5">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-blue-400">
            Accuracy Assessment
          </p>
          <p className="text-sm text-gray-700 leading-relaxed">{analyst.narrative_summary}</p>
          {analyst.summary_updated_at && (
            <p className="mt-2 text-xs text-gray-400">
              Updated {new Date(analyst.summary_updated_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })}
            </p>
          )}
        </div>
      )}

      {/* ── Notable Calls ─────────────────────────────────────────────────── */}
      {(calledIt.length > 0 || gotItWrong.length > 0) && (
        <div className="mt-8">
          <h2 className="mb-4 text-lg font-bold text-gray-900">Notable Calls</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {calledIt.length > 0 && (
              <div className="rounded-xl border border-green-200 bg-green-50 p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span className="rounded-full bg-green-500 px-2.5 py-0.5 text-xs font-bold text-white">✓ Called It</span>
                  <span className="text-xs text-gray-500">{calledIt.length} prediction{calledIt.length !== 1 ? "s" : ""}</span>
                </div>
                <ul className="space-y-3">
                  {calledIt.slice(0, 3).map((p) => (
                    <li key={p.id} className="text-sm text-gray-700 leading-snug">
                      &ldquo;{p.prediction_text}&rdquo;
                      {p.statement?.source_url && (
                        <a href={p.statement.source_url} target="_blank" rel="noopener noreferrer"
                          className="ml-1 text-xs text-green-700 hover:underline">
                          [{p.statement.source_title || "source"}]
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
                {calledIt.length > 3 && (
                  <p className="mt-2 text-xs text-green-600">+{calledIt.length - 3} more below</p>
                )}
              </div>
            )}

            {gotItWrong.length > 0 && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span className="rounded-full bg-red-500 px-2.5 py-0.5 text-xs font-bold text-white">✗ Got It Wrong</span>
                  <span className="text-xs text-gray-500">{gotItWrong.length} prediction{gotItWrong.length !== 1 ? "s" : ""}</span>
                </div>
                <ul className="space-y-3">
                  {gotItWrong.slice(0, 3).map((p) => (
                    <li key={p.id} className="text-sm text-gray-700 leading-snug">
                      &ldquo;{p.prediction_text}&rdquo;
                      {p.statement?.source_url && (
                        <a href={p.statement.source_url} target="_blank" rel="noopener noreferrer"
                          className="ml-1 text-xs text-red-700 hover:underline">
                          [{p.statement.source_title || "source"}]
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
                {gotItWrong.length > 3 && (
                  <p className="mt-2 text-xs text-red-600">+{gotItWrong.length - 3} more below</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── All Predictions ───────────────────────────────────────────────── */}
      <div className="mt-8">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-lg font-bold text-gray-900">
            Prediction Record
          </h2>
          <span className="text-sm text-gray-400">{predictions.length} total</span>
        </div>

        {predictions.length === 0 ? (
          <div className="rounded-xl border-2 border-dashed border-gray-200 p-10 text-center">
            <p className="text-gray-400">No predictions tracked yet.</p>
          </div>
        ) : (
          <div className="space-y-8">
            {Object.entries(bySource).map(([sourceType, preds]) => (
              <section key={sourceType}>
                <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-600">
                    {SOURCE_LABELS[sourceType] ?? sourceType}
                  </span>
                  <span>{preds.length} prediction{preds.length !== 1 ? "s" : ""}</span>
                </h3>
                <div className="space-y-3">
                  {preds.map((prediction) => (
                    <PredictionCard key={prediction.id} prediction={prediction} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      {/* Footer spacer */}
      <div className="h-16" />
    </div>
  );
}
