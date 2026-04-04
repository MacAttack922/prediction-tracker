"use client";

interface ScoreGaugeProps {
  score: number | null;
  total: number;
  finalized: number;
  letterGrade?: string | null;
  weightedScore?: number | null;
}

function getScoreColor(score: number): string {
  if (score >= 75) return "bg-green-500";
  if (score >= 50) return "bg-yellow-500";
  if (score >= 25) return "bg-orange-500";
  return "bg-red-500";
}

function getScoreTextColor(score: number): string {
  if (score >= 75) return "text-green-700";
  if (score >= 50) return "text-yellow-700";
  if (score >= 25) return "text-orange-700";
  return "text-red-700";
}

function getGradeColor(grade: string): string {
  if (grade.startsWith("A")) return "bg-green-100 text-green-800 border-green-200";
  if (grade.startsWith("B")) return "bg-blue-100 text-blue-800 border-blue-200";
  if (grade.startsWith("C")) return "bg-yellow-100 text-yellow-800 border-yellow-200";
  if (grade.startsWith("D")) return "bg-orange-100 text-orange-800 border-orange-200";
  return "bg-red-100 text-red-800 border-red-200";
}

export default function ScoreGauge({ score, total, finalized, letterGrade, weightedScore }: ScoreGaugeProps) {
  const hasScore = score !== null && score !== undefined;
  const displayScore = hasScore ? score : 0;
  const barWidth = hasScore ? `${displayScore}%` : "0%";
  const scoreColor = hasScore ? getScoreColor(displayScore) : "bg-gray-300";
  const textColor = hasScore ? getScoreTextColor(displayScore) : "text-gray-500";
  const showWeighted = weightedScore !== null && weightedScore !== undefined && weightedScore !== score;

  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between">
        <div className="flex items-end gap-3">
          <span className={`text-4xl font-bold ${textColor}`}>
            {hasScore ? `${displayScore}%` : "N/A"}
          </span>
          {letterGrade && (
            <span className={`mb-1 rounded border px-2 py-0.5 text-lg font-bold ${getGradeColor(letterGrade)}`}>
              {letterGrade}
            </span>
          )}
        </div>
        <span className="text-sm text-gray-500">
          {finalized} of {total} predictions rated
        </span>
      </div>

      {/* Bar gauge */}
      <div className="h-4 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className={`h-full rounded-full transition-all duration-700 ${scoreColor}`}
          style={{ width: barWidth }}
        />
      </div>

      <p className="text-sm text-gray-500">
        {hasScore
          ? `${displayScore}% accuracy based on ${finalized} finalized prediction${finalized !== 1 ? "s" : ""}${showWeighted ? ` · ${weightedScore}% lead-time weighted` : ""}`
          : "No finalized predictions yet — human review required to compute score"}
      </p>
    </div>
  );
}
