import type { RatingValue } from "@/lib/api";

interface RatingBadgeProps {
  rating: RatingValue | null;
  isPending?: boolean;
}

const RATING_CONFIG: Record<
  RatingValue,
  { label: string; bg: string; text: string; border: string }
> = {
  true: {
    label: "True",
    bg: "bg-green-100",
    text: "text-green-800",
    border: "border-green-300",
  },
  somewhat_true: {
    label: "Somewhat True",
    bg: "bg-yellow-100",
    text: "text-yellow-800",
    border: "border-yellow-300",
  },
  mostly_untrue: {
    label: "Mostly Untrue",
    bg: "bg-orange-100",
    text: "text-orange-800",
    border: "border-orange-300",
  },
  untrue: {
    label: "Untrue",
    bg: "bg-red-100",
    text: "text-red-800",
    border: "border-red-300",
  },
  unresolved: {
    label: "Unresolved",
    bg: "bg-gray-100",
    text: "text-gray-600",
    border: "border-gray-300",
  },
};

export default function RatingBadge({ rating, isPending = false }: RatingBadgeProps) {
  if (!rating) {
    return (
      <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs font-medium text-gray-400">
        Not Judged
      </span>
    );
  }

  const config = RATING_CONFIG[rating];
  const label = isPending ? `${config.label} (LLM)` : config.label;
  const opacity = isPending ? "opacity-75" : "";

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${config.bg} ${config.text} ${config.border} ${opacity}`}
    >
      {label}
    </span>
  );
}
