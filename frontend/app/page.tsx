"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchAnalysts, type Analyst } from "@/lib/api";
import AnalystCard from "@/components/AnalystCard";

type SortMode = "name" | "accuracy";

export default function HomePage() {
  const [analysts, setAnalysts] = useState<Analyst[]>([]);
  const [sort, setSort] = useState<SortMode>("name");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAnalysts("no-store")
      .then(setAnalysts)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load analysts"));
  }, []);

  const sorted = [...analysts].sort((a, b) => {
    if (sort === "accuracy") {
      const sa = a.score?.accuracy_score ?? -1;
      const sb = b.score?.accuracy_score ?? -1;
      return sb - sa;
    }
    return a.name.localeCompare(b.name);
  });

  return (
    <div>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Analyst Profiles</h1>
          <p className="mt-1 text-gray-500">
            {analysts.length > 0
              ? `Tracking ${analysts.length} analyst${analysts.length !== 1 ? "s" : ""} — predictions scored against the historical record`
              : "No analysts tracked yet."}
          </p>
        </div>
        <Link
          href="/admin/analysts/new"
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          + Add Analyst
        </Link>
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          <strong>Error:</strong> {error}
          <p className="mt-1 text-sm">
            Make sure the backend is running at{" "}
            <code className="rounded bg-red-100 px-1">http://localhost:8000</code>
          </p>
        </div>
      )}

      {analysts.length === 0 && !error && (
        <div className="rounded-xl border-2 border-dashed border-gray-300 p-12 text-center">
          <div className="text-4xl mb-3">📊</div>
          <h3 className="text-lg font-medium text-gray-700">No analysts yet</h3>
          <p className="mt-1 text-sm text-gray-500">Get started by adding an analyst in the admin dashboard.</p>
          <Link href="/admin/analysts/new" className="mt-4 inline-block rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700">
            Add Your First Analyst
          </Link>
        </div>
      )}

      {analysts.length > 0 && (
        <>
          {/* Sort toggle */}
          <div className="mb-4 flex items-center gap-2">
            <span className="text-sm text-gray-500">Sort by:</span>
            <div className="flex rounded-lg border border-gray-200 bg-white overflow-hidden text-sm">
              {(["name", "accuracy"] as SortMode[]).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setSort(mode)}
                  className={`px-4 py-1.5 font-medium transition-colors ${
                    sort === mode
                      ? "bg-blue-600 text-white"
                      : "text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {mode === "name" ? "Name" : "Accuracy"}
                </button>
              ))}
            </div>
            {sort === "accuracy" && (
              <span className="text-xs text-gray-400">Analysts without enough rated predictions appear last</span>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sorted.map((analyst) => (
              <AnalystCard key={analyst.id} analyst={analyst} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
