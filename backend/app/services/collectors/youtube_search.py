import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import httpx
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Statement, SourceType

if TYPE_CHECKING:
    from app.models import Analyst

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

_YT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _get_transcript(video_id: str, description: str = "") -> Optional[str]:
    """Attempt to get a video transcript; fall back to description snippet."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        joined = " ".join(seg.get("text", "") for seg in transcript_list)
        if joined.strip():
            return joined
    except Exception as exc:
        logger.debug(f"Transcript unavailable for {video_id}: {exc}")
    if len(description.strip()) >= 80:
        return f"[Video description] {description.strip()}"
    return None


def collect_youtube_guest_appearances(analyst: "Analyst", db: Session) -> int:
    """Search YouTube Data API for videos featuring the analyst on other channels."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.info("YOUTUBE_API_KEY not set — skipping YouTube guest search.")
        return 0

    # Resolve the analyst's own channel ID so we can exclude it from results
    own_channel_id = None
    if analyst.youtube_channel_id:
        try:
            from app.services.collectors.youtube import _resolve_channel_id
            own_channel_id = _resolve_channel_id(analyst.youtube_channel_id)
        except Exception:
            pass

    params = {
        "part": "snippet",
        "q": f'"{analyst.name}"',
        "type": "video",
        "key": api_key,
        "maxResults": 25,
        "relevanceLanguage": "en",
        "order": "date",
    }

    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(f"{YOUTUBE_API_BASE}/search", params=params)
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.error(f"YouTube Search API failed for {analyst.name}: {exc}")
        return 0

    new_count = 0
    for item in data.get("items", []):
        video_id = (item.get("id") or {}).get("videoId")
        if not video_id:
            continue

        snippet = item.get("snippet", {})

        # Skip videos on the analyst's own channel
        if own_channel_id and snippet.get("channelId") == own_channel_id:
            continue

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        title = snippet.get("title", "")
        channel_title = snippet.get("channelTitle", "")
        description = snippet.get("description", "")

        existing = (
            db.query(Statement)
            .filter(Statement.analyst_id == analyst.id, Statement.source_url == video_url)
            .first()
        )
        if existing:
            continue

        published_at = None
        published_str = snippet.get("publishedAt", "")
        if published_str:
            try:
                published_at = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass

        content = _get_transcript(video_id, description)
        if not content:
            logger.debug(f"No usable content for guest video {video_id}, skipping.")
            continue

        display_title = f"{channel_title}: {title}" if channel_title else title

        statement = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.youtube_guest,
            source_url=video_url,
            source_title=display_title,
            content=content,
            published_at=published_at,
            is_processed=False,
        )
        try:
            db.add(statement)
            db.commit()
            new_count += 1
        except IntegrityError:
            db.rollback()
            logger.debug(f"Duplicate YouTube guest statement skipped: {video_url}")
        except Exception as exc:
            db.rollback()
            logger.error(f"Error saving YouTube guest statement {video_url}: {exc}")

    logger.info(f"Collected {new_count} new YouTube guest appearances for {analyst.name}.")
    return new_count
