import Link from "next/link";
import type { Analyst } from "@/lib/api";

interface AnalystCardProps {
  analyst: Analyst;
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-gray-400";
  if (score >= 75) return "text-green-600";
  if (score >= 50) return "text-yellow-600";
  if (score >= 25) return "text-orange-600";
  return "text-red-600";
}

function scoreBg(score: number | null): string {
  if (score === null) return "bg-gray-50 border-gray-200";
  if (score >= 75) return "bg-green-50 border-green-200";
  if (score >= 50) return "bg-yellow-50 border-yellow-200";
  if (score >= 25) return "bg-orange-50 border-orange-200";
  return "bg-red-50 border-red-200";
}

function gradeBg(grade: string | null): string {
  if (!grade) return "";
  if (grade.startsWith("A")) return "text-green-700";
  if (grade.startsWith("B")) return "text-blue-700";
  if (grade.startsWith("C")) return "text-yellow-700";
  if (grade.startsWith("D")) return "text-orange-700";
  return "text-red-700";
}

export default function AnalystCard({ analyst }: AnalystCardProps) {
  const score = analyst.score?.accuracy_score ?? null;
  const total = analyst.score?.total_predictions ?? 0;
  const finalized = analyst.score?.finalized_predictions ?? 0;
  const grade = analyst.score?.letter_grade ?? null;

  return (
    <Link
      href={`/analysts/${analyst.slug}`}
      className="block rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: photo + name + bio */}
        <div className="min-w-0 flex-1 flex items-start gap-3">
          {analyst.profile_image_url ? (
            <img
              src={analyst.profile_image_url}
              alt={analyst.name}
              className="h-12 w-12 rounded-full object-cover border border-gray-200 shrink-0"
            />
          ) : (
            <div className="h-12 w-12 rounded-full bg-gray-100 border border-gray-200 flex items-center justify-center text-gray-400 font-bold text-lg shrink-0">
              {analyst.name.charAt(0)}
            </div>
          )}
          <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-semibold text-gray-900">{analyst.name}</h2>
          {analyst.bio && (
            <p className="mt-1 line-clamp-2 text-sm text-gray-500">{analyst.bio}</p>
          )}

          {/* Source badges */}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {analyst.substack_url && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                Substack
              </span>
            )}
            {analyst.youtube_channel_id && (
              <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
                YouTube
              </span>
            )}
            {analyst.website_url && (
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
                Web
              </span>
            )}
          </div>
          </div>
        </div>

        {/* Right: score box */}
        <div
          className={`flex min-w-[80px] flex-col items-center rounded-lg border px-3 py-2 text-center ${scoreBg(score)}`}
        >
          {grade ? (
            <span className={`text-3xl font-bold ${gradeBg(grade)}`}>{grade}</span>
          ) : (
            <span className="text-3xl font-bold text-gray-300">—</span>
          )}
          {score !== null && (
            <span className={`text-sm font-semibold ${scoreColor(score)}`}>{score}%</span>
          )}
          <span className="mt-1 text-xs text-gray-400">
            {total} prediction{total !== 1 ? "s" : ""}
          </span>
          {finalized > 0 && (
            <span className="text-xs text-gray-400">{finalized} rated</span>
          )}
        </div>
      </div>
    </Link>
  );
}
