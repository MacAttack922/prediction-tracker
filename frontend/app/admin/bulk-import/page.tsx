"use client";

import { useState, useEffect, FormEvent } from "react";
import Link from "next/link";
import {
  fetchAnalysts,
  bulkImport,
  type Analyst,
  type BulkImportResult,
} from "@/lib/api";

const SOURCE_OPTIONS = [
  { value: "website", label: "Website" },
  { value: "google_news", label: "Google News" },
  { value: "youtube", label: "YouTube" },
  { value: "substack", label: "Substack" },
  { value: "cnbc", label: "CNBC" },
];

export default function BulkImportPage() {
  const [analysts, setAnalysts] = useState<Analyst[]>([]);
  const [analystId, setAnalystId] = useState<string>("");
  const [sourceType, setSourceType] = useState("website");
  const [urlsText, setUrlsText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<BulkImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingAnalysts, setLoadingAnalysts] = useState(true);

  useEffect(() => {
    fetchAnalysts()
      .then((data) => {
        setAnalysts(data);
        if (data.length > 0) setAnalystId(String(data[0].id));
      })
      .catch(() => {})
      .finally(() => setLoadingAnalysts(false));
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!analystId) {
      setError("Please select an analyst.");
      return;
    }

    const urls = urlsText
      .split("\n")
      .map((u) => u.trim())
      .filter((u) => u.length > 0);

    if (urls.length === 0) {
      setError("Please enter at least one URL.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const res = await bulkImport({
        analyst_id: parseInt(analystId),
        urls,
        source_type: sourceType,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Link
        href="/admin"
        className="mb-6 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
      >
        <svg
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Admin
      </Link>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold text-gray-900">Bulk URL Import</h1>
        <p className="mt-1 text-sm text-gray-500">
          Paste one URL per line. Each page will be fetched and stored as a statement.
        </p>

        {error && (
          <div className="mt-4 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Analyst <span className="text-red-500">*</span>
            </label>
            {loadingAnalysts ? (
              <p className="mt-1 text-sm text-gray-400">Loading analysts...</p>
            ) : (
              <select
                value={analystId}
                onChange={(e) => setAnalystId(e.target.value)}
                required
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                {analysts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Source Type</label>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {SOURCE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              URLs <span className="text-red-500">*</span>
              <span className="ml-1 font-normal text-gray-400">(one per line)</span>
            </label>
            <textarea
              rows={10}
              value={urlsText}
              onChange={(e) => setUrlsText(e.target.value)}
              placeholder={"https://example.com/article-1\nhttps://example.com/article-2"}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <p className="mt-1 text-xs text-gray-400">
              {urlsText.split("\n").filter((u) => u.trim().length > 0).length} URL(s) entered
            </p>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={submitting || loadingAnalysts}
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {submitting ? "Importing..." : "Import URLs"}
            </button>
            <Link href="/admin" className="text-sm text-gray-500 hover:text-gray-700">
              Cancel
            </Link>
          </div>
        </form>

        {result && (
          <div className="mt-6 rounded-lg border border-gray-200 bg-gray-50 p-4">
            <h2 className="text-sm font-semibold text-gray-800">Import Results</h2>
            <div className="mt-3 grid grid-cols-3 gap-4 text-center">
              <div className="rounded-lg bg-green-50 border border-green-200 p-3">
                <p className="text-2xl font-bold text-green-700">{result.imported}</p>
                <p className="text-xs text-green-600 mt-0.5">Imported</p>
              </div>
              <div className="rounded-lg bg-gray-100 border border-gray-200 p-3">
                <p className="text-2xl font-bold text-gray-600">{result.skipped}</p>
                <p className="text-xs text-gray-500 mt-0.5">Skipped</p>
              </div>
              <div className="rounded-lg bg-red-50 border border-red-200 p-3">
                <p className="text-2xl font-bold text-red-600">{result.failed.length}</p>
                <p className="text-xs text-red-500 mt-0.5">Failed</p>
              </div>
            </div>

            {result.failed.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-medium text-gray-600 mb-1">Failed URLs:</p>
                <ul className="space-y-1">
                  {result.failed.map((url) => (
                    <li key={url} className="text-xs text-red-600 font-mono break-all">
                      {url}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
