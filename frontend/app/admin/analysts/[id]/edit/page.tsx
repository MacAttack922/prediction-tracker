"use client";

import { useState, useEffect, FormEvent } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { fetchAnalysts, updateAnalyst, fetchPhoto, type Analyst } from "@/lib/api";

export default function EditAnalystPage() {
  const router = useRouter();
  const params = useParams();
  const analystId = parseInt(params.id as string);

  const [analyst, setAnalyst] = useState<Analyst | null>(null);
  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [substackUrl, setSubstackUrl] = useState("");
  const [youtubeChannelId, setYoutubeChannelId] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [podcastRssUrl, setPodcastRssUrl] = useState("");
  const [twitterHandle, setTwitterHandle] = useState("");
  const [profileImageUrl, setProfileImageUrl] = useState("");

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [fetchingPhoto, setFetchingPhoto] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetchAnalysts().then((analysts) => {
      const a = analysts.find((x) => x.id === analystId);
      if (a) {
        setAnalyst(a);
        setName(a.name ?? "");
        setBio(a.bio ?? "");
        setSubstackUrl(a.substack_url ?? "");
        setYoutubeChannelId(a.youtube_channel_id ?? "");
        setWebsiteUrl(a.website_url ?? "");
        setPodcastRssUrl(a.podcast_rss_url ?? "");
        setTwitterHandle(a.twitter_handle ?? "");
        setProfileImageUrl(a.profile_image_url ?? "");
      }
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [analystId]);

  async function handleFetchPhoto() {
    setFetchingPhoto(true);
    setPhotoError(null);
    try {
      const updated = await fetchPhoto(analystId);
      setProfileImageUrl(updated.profile_image_url ?? "");
    } catch (err) {
      setPhotoError(err instanceof Error ? err.message : "No photo found");
    } finally {
      setFetchingPhoto(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSaved(false);
    try {
      await updateAnalyst(analystId, {
        name: name.trim() || undefined,
        bio: bio.trim() || undefined,
        substack_url: substackUrl.trim() || undefined,
        youtube_channel_id: youtubeChannelId.trim() || undefined,
        website_url: websiteUrl.trim() || undefined,
        podcast_rss_url: podcastRssUrl.trim() || undefined,
        twitter_handle: twitterHandle.trim() || undefined,
        profile_image_url: profileImageUrl.trim() || undefined,
      });
      setSaved(true);
      setTimeout(() => router.push("/admin"), 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="text-center py-12 text-gray-400">Loading...</div>;
  if (!analyst) return <div className="text-center py-12 text-gray-500">Analyst not found.</div>;

  return (
    <div className="mx-auto max-w-xl">
      <Link href="/admin" className="mb-6 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Admin
      </Link>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold text-gray-900">Edit Analyst</h1>

        {error && (
          <div className="mt-4 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">{error}</div>
        )}
        {saved && (
          <div className="mt-4 rounded-lg bg-green-50 border border-green-200 p-3 text-sm text-green-700">Saved — redirecting...</div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          {/* Photo */}
          <div>
            <label className="block text-sm font-medium text-gray-700">Profile Photo</label>
            <div className="mt-2 flex items-center gap-4">
              {profileImageUrl ? (
                <img
                  src={profileImageUrl}
                  alt={name}
                  className="h-16 w-16 rounded-full object-cover border border-gray-200"
                />
              ) : (
                <div className="h-16 w-16 rounded-full bg-gray-100 border border-gray-200 flex items-center justify-center text-gray-400 text-xl font-bold">
                  {name.charAt(0)}
                </div>
              )}
              <div className="flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={handleFetchPhoto}
                  disabled={fetchingPhoto}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  {fetchingPhoto ? "Fetching..." : "Fetch from Wikipedia"}
                </button>
                {photoError && <p className="text-xs text-red-500">{photoError}</p>}
              </div>
            </div>
            <input
              type="text"
              value={profileImageUrl}
              onChange={(e) => setProfileImageUrl(e.target.value)}
              placeholder="Or paste an image URL directly"
              className="mt-2 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Name <span className="text-red-500">*</span></label>
            <input type="text" required value={name} onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Bio</label>
            <textarea rows={3} value={bio} onChange={(e) => setBio(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>

          <div className="border-t border-gray-100 pt-4">
            <p className="mb-3 text-sm font-medium text-gray-700">Data Sources</p>
            <div className="space-y-4">
              {[
                { label: "Substack URL", value: substackUrl, set: setSubstackUrl, placeholder: "https://username.substack.com" },
                { label: "YouTube Channel or Handle", value: youtubeChannelId, set: setYoutubeChannelId, placeholder: "@handle or channel URL" },
                { label: "Website URL", value: websiteUrl, set: setWebsiteUrl, placeholder: "https://example.com" },
                { label: "Podcast RSS URL", value: podcastRssUrl, set: setPodcastRssUrl, placeholder: "https://feeds.example.com/podcast.rss" },
                { label: "Twitter/X Handle", value: twitterHandle, set: setTwitterHandle, placeholder: "@username" },
              ].map(({ label, value, set, placeholder }) => (
                <div key={label}>
                  <label className="block text-sm text-gray-600">{label}</label>
                  <input type="text" value={value} onChange={(e) => set(e.target.value)} placeholder={placeholder}
                    className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500" />
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button type="submit" disabled={submitting}
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {submitting ? "Saving..." : "Save Changes"}
            </button>
            <Link href="/admin" className="text-sm text-gray-500 hover:text-gray-700">Cancel</Link>
          </div>
        </form>
      </div>
    </div>
  );
}
