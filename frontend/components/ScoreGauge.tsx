"use client";

interface ScoreGaugeProps {
  score: number | null;
  total: number;
  finalized: number;
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

export default function ScoreGauge({ score, total, finalized }: ScoreGaugeProps) {
  const hasScore = score !== null && score !== undefined;
  const displayScore = hasScore ? score : 0;
  const barWidth = hasScore ? `${displayScore}%` : "0%";
  const scoreColor = hasScore ? getScoreColor(displayScore) : "bg-gray-300";
  const textColor = hasScore ? getScoreTextColor(displayScore) : "text-gray-500";

  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between">
        <span className={`text-4xl font-bold ${textColor}`}>
          {hasScore ? `${displayScore}%` : "N/A"}
        </span>
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
          ? `${displayScore}% accuracy based on ${finalized} finalized prediction${finalized !== 1 ? "s" : ""}`
          : "No finalized predictions yet — human review required to compute score"}
      </p>
    </div>
  );
}
