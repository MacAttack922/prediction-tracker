import { notFound } from "next/navigation";
import Link from "next/link";
import { fetchAnalyst } from "@/lib/api";
import ScoreGauge from "@/components/ScoreGauge";
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

export default async function AnalystProfilePage({ params }: Props) {
  let analyst;
  try {
    analyst = await fetchAnalyst(params.slug, "no-store");
  } catch (err) {
    notFound();
  }

  const score = analyst.score;
  const predictions = analyst.predictions ?? [];

  // Group by source type
  const bySource: Record<string, Prediction[]> = {};
  for (const p of predictions) {
    const key = p.statement?.source_type ?? "unknown";
    if (!bySource[key]) bySource[key] = [];
    bySource[key].push(p);
  }

  // Notable calls: finalized predictions with true or untrue human_rating
  const calledIt = predictions.filter(
    (p) => p.outcome?.is_finalized && p.outcome?.human_rating === "true"
  );
  const gotItWrong = predictions.filter(
    (p) => p.outcome?.is_finalized && p.outcome?.human_rating === "untrue"
  );
  const hasNotableCalls = calledIt.length > 0 || gotItWrong.length > 0;

  // Rating breakdown for the summary bar
  const breakdown = score?.rating_breakdown ?? {};

  return (
    <div>
      {/* Back link */}
      <Link href="/" className="mb-6 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        All Analysts
      </Link>

      {/* Profile header */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
          {/* Info */}
          <div className="flex-1">
            <div className="flex items-center gap-4">
              {analyst.profile_image_url && (
                <img
                  src={analyst.profile_image_url}
                  alt={analyst.name}
                  className="h-16 w-16 rounded-full object-cover border border-gray-200 shrink-0"
                />
              )}
              <h1 className="text-2xl font-bold text-gray-900">{analyst.name}</h1>
            </div>
            {analyst.bio && (
              <p className="mt-2 text-gray-600 leading-relaxed">{analyst.bio}</p>
            )}

            {analyst.narrative_summary && (
              <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-4">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-blue-400">
                  Accuracy Assessment
                </p>
                <p className="text-sm text-gray-700 leading-relaxed">
                  {analyst.narrative_summary}
                </p>
                {analyst.summary_updated_at && (
                  <p className="mt-2 text-xs text-gray-400">
                    Last updated {new Date(analyst.summary_updated_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })}
                  </p>
                )}
              </div>
            )}

            {/* Links */}
            <div className="mt-3 flex flex-wrap gap-3 text-sm">
              {analyst.substack_url && (
                <a
                  href={analyst.substack_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-amber-700 hover:underline"
                >
                  <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium">Substack</span>
                </a>
              )}
              {analyst.youtube_channel_id && (
                <a
                  href={`https://www.youtube.com/channel/${analyst.youtube_channel_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 hover:underline"
                >
                  YouTube
                </a>
              )}
              {analyst.website_url && (
                <a
                  href={analyst.website_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 hover:underline"
                >
                  Website
                </a>
              )}
            </div>
          </div>

          {/* Score gauge */}
          <div className="w-full sm:w-72">
            <ScoreGauge
              score={score?.accuracy_score ?? null}
              total={score?.total_predictions ?? 0}
              finalized={score?.finalized_predictions ?? 0}
            />
          </div>
        </div>

        {/* Rating breakdown mini-bar */}
        {score && score.finalized_predictions > 0 && (
          <div className="mt-4 border-t border-gray-100 pt-4">
            <div className="grid grid-cols-5 gap-2 text-center text-xs">
              {[
                { key: "true", label: "True", color: "bg-green-500" },
                { key: "somewhat_true", label: "Somewhat True", color: "bg-yellow-500" },
                { key: "mostly_untrue", label: "Mostly Untrue", color: "bg-orange-500" },
                { key: "untrue", label: "Untrue", color: "bg-red-500" },
                { key: "unresolved", label: "Unresolved", color: "bg-gray-400" },
              ].map(({ key, label, color }) => (
                <div key={key} className="flex flex-col items-center gap-1">
                  <span className="text-lg font-bold text-gray-800">
                    {breakdown[key] ?? 0}
                  </span>
                  <div className={`h-2 w-full rounded-full ${color} opacity-80`} />
                  <span className="text-gray-500 leading-tight">{label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Notable Calls */}
      {hasNotableCalls && (
        <div className="mt-8">
          <h2 className="mb-4 text-xl font-semibold text-gray-900">Notable Calls</h2>
          <div className="space-y-6">
            {calledIt.length > 0 && (
              <section>
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-green-600">
                  <span className="rounded bg-green-100 px-2 py-0.5">Called It</span>
                  <span className="text-gray-400 normal-case font-normal tracking-normal">
                    {calledIt.length} prediction{calledIt.length !== 1 ? "s" : ""}
                  </span>
                </h3>
                <div className="space-y-2">
                  {calledIt.map((p) => (
                    <div key={p.id} className="flex items-start gap-3 rounded-lg border border-green-200 bg-green-50 p-4">
                      <span className="mt-0.5 shrink-0 rounded-full bg-green-500 px-2 py-0.5 text-xs font-semibold text-white">True</span>
                      <div className="flex-1">
                        <p className="text-sm text-gray-800 leading-relaxed">{p.prediction_text}</p>
                        {p.statement?.source_url && (
                          <a href={p.statement.source_url} target="_blank" rel="noopener noreferrer"
                            className="mt-1 inline-block text-xs text-green-700 hover:underline truncate max-w-xs">
                            {p.statement.source_title || p.statement.source_url}
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
            {gotItWrong.length > 0 && (
              <section>
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-red-600">
                  <span className="rounded bg-red-100 px-2 py-0.5">Got It Wrong</span>
                  <span className="text-gray-400 normal-case font-normal tracking-normal">
                    {gotItWrong.length} prediction{gotItWrong.length !== 1 ? "s" : ""}
                  </span>
                </h3>
                <div className="space-y-2">
                  {gotItWrong.map((p) => (
                    <div key={p.id} className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
                      <span className="mt-0.5 shrink-0 rounded-full bg-red-500 px-2 py-0.5 text-xs font-semibold text-white">Untrue</span>
                      <div className="flex-1">
                        <p className="text-sm text-gray-800 leading-relaxed">{p.prediction_text}</p>
                        {p.statement?.source_url && (
                          <a href={p.statement.source_url} target="_blank" rel="noopener noreferrer"
                            className="mt-1 inline-block text-xs text-red-700 hover:underline truncate max-w-xs">
                            {p.statement.source_title || p.statement.source_url}
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </div>
      )}

      {/* Predictions */}
      <div className="mt-8">
        <h2 className="mb-4 text-xl font-semibold text-gray-900">
          Predictions{" "}
          <span className="ml-1 text-base font-normal text-gray-400">
            ({predictions.length} total)
          </span>
        </h2>

        {predictions.length === 0 ? (
          <div className="rounded-xl border-2 border-dashed border-gray-200 p-8 text-center text-gray-400">
            No predictions extracted yet. Use the admin panel to collect data and run extraction.
          </div>
        ) : (
          <div className="space-y-8">
            {/* All predictions grouped by source */}
            {Object.entries(bySource).map(([sourceType, preds]) => (
              <section key={sourceType}>
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
                  <span className="rounded bg-gray-100 px-2 py-0.5">
                    {SOURCE_LABELS[sourceType] ?? sourceType}
                  </span>
                  <span className="text-gray-400 normal-case font-normal tracking-normal">
                    {preds.length} prediction{preds.length !== 1 ? "s" : ""}
                  </span>
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
    </div>
  );
}
