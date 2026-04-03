"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createAnalyst, lookupAnalyst } from "@/lib/api";

export default function NewAnalystPage() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [substackUrl, setSubstackUrl] = useState("");
  const [youtubeChannelId, setYoutubeChannelId] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [podcastRssUrl, setPodcastRssUrl] = useState("");
  const [twitterHandle, setTwitterHandle] = useState("");

  const [looking, setLooking] = useState(false);
  const [lookupDone, setLookupDone] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function handleLookup() {
    if (!name.trim()) return;
    setLooking(true);
    setLookupError(null);
    setLookupDone(false);
    try {
      const result = await lookupAnalyst(name.trim());
      if (result.bio) setBio(result.bio);
      if (result.substack_url) setSubstackUrl(result.substack_url);
      if (result.youtube_channel_id) setYoutubeChannelId(result.youtube_channel_id);
      if (result.website_url) setWebsiteUrl(result.website_url);
      if (result.podcast_rss_url) setPodcastRssUrl(result.podcast_rss_url);
      setLookupDone(true);
    } catch (err) {
      setLookupError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setLooking(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await createAnalyst({
        name: name.trim(),
        bio: bio.trim() || undefined,
        substack_url: substackUrl.trim() || undefined,
        youtube_channel_id: youtubeChannelId.trim() || undefined,
        website_url: websiteUrl.trim() || undefined,
        podcast_rss_url: podcastRssUrl.trim() || undefined,
        twitter_handle: twitterHandle.trim() || undefined,
      });
      router.push("/admin");
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create analyst");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <Link href="/admin" className="mb-6 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Admin
      </Link>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold text-gray-900">Add New Analyst</h1>
        <p className="mt-1 text-sm text-gray-500">
          Enter a name and click <strong>Look up</strong> to auto-fill their sources, or fill them in manually.
        </p>

        {submitError && (
          <div className="mt-4 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {submitError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          {/* Name + lookup button */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700">
              Name <span className="text-red-500">*</span>
            </label>
            <div className="mt-1 flex gap-2">
              <input
                id="name"
                type="text"
                required
                value={name}
                onChange={(e) => { setName(e.target.value); setLookupDone(false); }}
                placeholder="e.g. Jane Smith"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={handleLookup}
                disabled={!name.trim() || looking}
                className="shrink-0 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {looking ? (
                  <span className="flex items-center gap-1.5">
                    <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                    Looking up...
                  </span>
                ) : "Look up"}
              </button>
            </div>
            {lookupDone && (
              <p className="mt-1.5 text-xs text-green-600">Fields auto-filled — review and edit as needed.</p>
            )}
            {lookupError && (
              <p className="mt-1.5 text-xs text-red-600">{lookupError}</p>
            )}
          </div>

          {/* Bio */}
          <div>
            <label htmlFor="bio" className="block text-sm font-medium text-gray-700">Bio</label>
            <textarea
              id="bio"
              rows={3}
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              placeholder="Brief description of who this analyst is and their area of expertise..."
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Sources */}
          <div className="border-t border-gray-100 pt-4">
            <p className="mb-3 text-sm font-medium text-gray-700">Data Sources</p>
            <div className="space-y-4">
              <div>
                <label htmlFor="substack_url" className="block text-sm text-gray-600">Substack URL</label>
                <input
                  id="substack_url"
                  type="text"
                  value={substackUrl}
                  onChange={(e) => setSubstackUrl(e.target.value)}
                  placeholder="https://username.substack.com"
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
              <div>
                <label htmlFor="youtube_channel_id" className="block text-sm text-gray-600">YouTube Channel or Handle</label>
                <input
                  id="youtube_channel_id"
                  type="text"
                  value={youtubeChannelId}
                  onChange={(e) => setYoutubeChannelId(e.target.value)}
                  placeholder="@handle or channel URL"
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <p className="mt-0.5 text-xs text-gray-400">Handles, full URLs, and channel IDs are all accepted.</p>
              </div>
              <div>
                <label htmlFor="website_url" className="block text-sm text-gray-600">Website URL</label>
                <input
                  id="website_url"
                  type="text"
                  value={websiteUrl}
                  onChange={(e) => setWebsiteUrl(e.target.value)}
                  placeholder="https://example.com"
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
              <div>
                <label htmlFor="podcast_rss_url" className="block text-sm text-gray-600">Podcast RSS URL</label>
                <input
                  id="podcast_rss_url"
                  type="text"
                  value={podcastRssUrl}
                  onChange={(e) => setPodcastRssUrl(e.target.value)}
                  placeholder="https://feeds.example.com/podcast.rss"
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <p className="mt-0.5 text-xs text-gray-400">Transcripts fetched automatically when available.</p>
              </div>
              <div>
                <label htmlFor="twitter_handle" className="block text-sm text-gray-600">Twitter/X Handle</label>
                <input
                  id="twitter_handle"
                  type="text"
                  value={twitterHandle}
                  onChange={(e) => setTwitterHandle(e.target.value)}
                  placeholder="@handle"
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Creating..." : "Create Analyst"}
            </button>
            <Link href="/admin" className="text-sm text-gray-500 hover:text-gray-700">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
