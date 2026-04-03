"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  fetchAnalysts,
  collectData,
  processStatements,
  judgeAnalyst,
  regenerateSummary,
  fetchReviewQueue,
  type Analyst,
  type CollectResult,
  type ProcessResult,
  type JudgeResult,
} from "@/lib/api";

type ActionState = "idle" | "loading" | "success" | "error";

interface AnalystActions {
  collect: ActionState;
  process: ActionState;
  judge: ActionState;
  summarize: ActionState;
  collectResult?: CollectResult;
  processResult?: ProcessResult;
  judgeResult?: JudgeResult;
  errorMsg?: string;
}

export default function AdminDashboard() {
  const [analysts, setAnalysts] = useState<Analyst[]>([]);
  const [queueCount, setQueueCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<Record<number, AnalystActions>>({});

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, q] = await Promise.all([fetchAnalysts("no-store"), fetchReviewQueue()]);
      setAnalysts(a);
      setQueueCount(q.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  function setActionState(analystId: number, action: keyof AnalystActions, value: ActionState) {
    setActions((prev) => ({
      ...prev,
      [analystId]: { ...prev[analystId], [action]: value },
    }));
  }

  async function handleCollect(analyst: Analyst) {
    setActionState(analyst.id, "collect", "loading");
    try {
      const result = await collectData(analyst.id);
      setActions((prev) => ({
        ...prev,
        [analyst.id]: {
          ...prev[analyst.id],
          collect: "success",
          collectResult: result,
        },
      }));
      loadData();
    } catch (err) {
      setActions((prev) => ({
        ...prev,
        [analyst.id]: {
          ...prev[analyst.id],
          collect: "error",
          errorMsg: err instanceof Error ? err.message : "Error",
        },
      }));
    }
  }

  async function handleProcess(analyst: Analyst) {
    setActionState(analyst.id, "process", "loading");
    try {
      const result = await processStatements(analyst.id);
      setActions((prev) => ({
        ...prev,
        [analyst.id]: {
          ...prev[analyst.id],
          process: "success",
          processResult: result,
        },
      }));
      loadData();
    } catch (err) {
      setActions((prev) => ({
        ...prev,
        [analyst.id]: {
          ...prev[analyst.id],
          process: "error",
          errorMsg: err instanceof Error ? err.message : "Error",
        },
      }));
    }
  }

  async function handleJudge(analyst: Analyst) {
    setActionState(analyst.id, "judge", "loading");
    try {
      const result = await judgeAnalyst(analyst.id);
      setActions((prev) => ({
        ...prev,
        [analyst.id]: {
          ...prev[analyst.id],
          judge: "success",
          judgeResult: result,
        },
      }));
      loadData();
    } catch (err) {
      setActions((prev) => ({
        ...prev,
        [analyst.id]: {
          ...prev[analyst.id],
          judge: "error",
          errorMsg: err instanceof Error ? err.message : "Error",
        },
      }));
    }
  }

  async function handleSummarize(analyst: Analyst) {
    setActionState(analyst.id, "summarize", "loading");
    try {
      await regenerateSummary(analyst.id);
      setActions((prev) => ({
        ...prev,
        [analyst.id]: { ...prev[analyst.id], summarize: "success" },
      }));
      loadData();
    } catch (err) {
      setActions((prev) => ({
        ...prev,
        [analyst.id]: {
          ...prev[analyst.id],
          summarize: "error",
          errorMsg: err instanceof Error ? err.message : "Error",
        },
      }));
    }
  }

  return (
    <div>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">Manage analysts, collect data, and review predictions</p>
        </div>
        <div className="flex gap-3">
          <Link
            href="/admin/review"
            className="relative rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Review Queue
            {queueCount !== null && queueCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white">
                {queueCount > 99 ? "99+" : queueCount}
              </span>
            )}
          </Link>
          <Link
            href="/admin/paste"
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Paste Text
          </Link>
          <Link
            href="/admin/bulk-import"
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Bulk Import
          </Link>
          <Link
            href="/admin/analysts/new"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            + Add Analyst
          </Link>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard label="Analysts" value={analysts.length} color="blue" />
        <StatCard
          label="Total Predictions"
          value={analysts.reduce((s, a) => s + (a.score?.total_predictions ?? 0), 0)}
          color="purple"
        />
        <StatCard
          label="Pending Review"
          value={queueCount ?? "—"}
          color="orange"
        />
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading...</div>
      ) : analysts.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-gray-200 p-10 text-center">
          <p className="text-gray-500">No analysts yet.</p>
          <Link href="/admin/analysts/new" className="mt-3 inline-block text-blue-600 hover:underline text-sm">
            Add your first analyst
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {analysts.map((analyst) => {
            const a = actions[analyst.id] ?? {};
            return (
              <div
                key={analyst.id}
                className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      {analyst.profile_image_url && (
                        <img src={analyst.profile_image_url} alt={analyst.name}
                          className="h-8 w-8 rounded-full object-cover border border-gray-200" />
                      )}
                      <Link
                        href={`/analysts/${analyst.slug}`}
                        className="text-lg font-semibold text-gray-900 hover:text-blue-600"
                      >
                        {analyst.name}
                      </Link>
                      <span className="text-xs text-gray-400">/{analyst.slug}</span>
                      <Link
                        href={`/admin/analysts/${analyst.id}/edit`}
                        className="text-xs text-blue-500 hover:underline"
                      >
                        Edit
                      </Link>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500">
                      <span>{analyst.score?.total_predictions ?? 0} predictions</span>
                      <span>{analyst.score?.judged_predictions ?? 0} judged</span>
                      <span>{analyst.score?.finalized_predictions ?? 0} finalized</span>
                      {analyst.score?.accuracy_score !== null && (
                        <span className="font-medium text-gray-700">
                          {analyst.score?.accuracy_score}% accuracy
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex flex-wrap gap-2">
                    <ActionButton
                      label="Collect Data"
                      state={a.collect ?? "idle"}
                      onClick={() => handleCollect(analyst)}
                      successText={
                        a.collectResult
                          ? `+${a.collectResult.total_new} new (${a.collectResult.total_statements} total)`
                          : "Done"
                      }
                    />
                    <ActionButton
                      label="Process Statements"
                      state={a.process ?? "idle"}
                      onClick={() => handleProcess(analyst)}
                      successText={
                        a.processResult
                          ? `${a.processResult.predictions_extracted} extracted`
                          : "Done"
                      }
                    />
                    <ActionButton
                      label="Judge Predictions"
                      state={a.judge ?? "idle"}
                      onClick={() => handleJudge(analyst)}
                      successText={
                        a.judgeResult
                          ? `${a.judgeResult.predictions_judged} judged`
                          : "Done"
                      }
                    />
                    <ActionButton
                      label="Regenerate Summary"
                      state={a.summarize ?? "idle"}
                      onClick={() => handleSummarize(analyst)}
                      successText="Summary updated"
                    />
                  </div>
                </div>

                {a.errorMsg && (
                  <p className="mt-2 text-xs text-red-600">{a.errorMsg}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color: "blue" | "purple" | "orange" | "green";
}) {
  const colorMap = {
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    purple: "bg-purple-50 border-purple-200 text-purple-700",
    orange: "bg-orange-50 border-orange-200 text-orange-700",
    green: "bg-green-50 border-green-200 text-green-700",
  };
  return (
    <div className={`rounded-lg border p-4 ${colorMap[color]}`}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="mt-0.5 text-sm opacity-80">{label}</p>
    </div>
  );
}

function ActionButton({
  label,
  state,
  onClick,
  successText,
}: {
  label: string;
  state: ActionState;
  onClick: () => void;
  successText: string;
}) {
  const disabled = state === "loading";

  if (state === "success") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-green-100 px-3 py-1.5 text-xs font-medium text-green-800">
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
        {successText}
      </span>
    );
  }

  if (state === "error") {
    return (
      <button
        onClick={onClick}
        className="rounded-md bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 border border-red-200"
      >
        Retry: {label}
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      {state === "loading" ? (
        <span className="flex items-center gap-1.5">
          <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          Working...
        </span>
      ) : (
        label
      )}
    </button>
  );
}
