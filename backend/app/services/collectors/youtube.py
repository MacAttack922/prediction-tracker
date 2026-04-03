import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import feedparser
import httpx
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Statement, SourceType

if TYPE_CHECKING:
    from app.models import Analyst

logger = logging.getLogger(__name__)

_YT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _resolve_channel_id(raw: str) -> Optional[str]:
    """Accept a channel ID, @handle, or youtube.com URL and return a bare channel ID."""
    # Already a bare channel ID
    if re.match(r'^UC[A-Za-z0-9_-]{20,}$', raw):
        return raw

    # Strip query string and whitespace
    raw = raw.strip().split('?')[0].rstrip('/')

    # Extract handle or channel path
    handle_match = re.search(r'@([\w.-]+)', raw)
    channel_match = re.search(r'channel/(UC[A-Za-z0-9_-]+)', raw)

    if channel_match:
        return channel_match.group(1)

    # Resolve handle via YouTube page
    handle = handle_match.group(0) if handle_match else raw if raw.startswith('@') else f'@{raw}'
    lookup_url = f"https://www.youtube.com/{handle}"
    try:
        with httpx.Client(follow_redirects=True, timeout=10, headers=_YT_HEADERS) as client:
            r = client.get(lookup_url)
        match = re.search(r'channel/(UC[A-Za-z0-9_-]+)', r.text)
        if match:
            return match.group(1)
    except Exception as exc:
        logger.warning(f"Could not resolve YouTube handle {handle}: {exc}")

    return None


def retry_youtube_transcripts(analyst: "Analyst", db: Session) -> int:
    """For statements that only have a description fallback, try to fetch the real transcript."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return 0

    # Find youtube statements for this analyst that only have description fallback content
    stubs = (
        db.query(Statement)
        .filter(
            Statement.analyst_id == analyst.id,
            Statement.source_type == SourceType.youtube,
            Statement.content.like("[Video description]%"),
        )
        .all()
    )

    upgraded = 0
    for stmt in stubs:
        # Extract video ID from URL
        video_id = None
        if "v=" in (stmt.source_url or ""):
            video_id = stmt.source_url.split("v=")[-1].split("&")[0]
        if not video_id:
            continue

        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            joined = " ".join(seg.get("text", "") for seg in transcript_list)
            if joined.strip():
                stmt.content = joined
                stmt.is_processed = False  # queue for re-extraction
                db.commit()
                upgraded += 1
                logger.info(f"Upgraded transcript for video {video_id}")
                continue
        except Exception as exc:
            logger.debug(f"Transcript still unavailable for {video_id}: {exc}")

        # Try Whisper transcription before giving up
        try:
            from app.services.transcriber import transcribe_youtube
            whisper_content = transcribe_youtube(video_id)
            if whisper_content and len(whisper_content.strip()) > 50:
                stmt.content = whisper_content
                stmt.is_processed = False
                db.commit()
                upgraded += 1
                logger.info(f"Upgraded transcript via Whisper for video {video_id}")
        except Exception as exc:
            logger.debug(f"Whisper transcription failed for {video_id}: {exc}")

    logger.info(f"Upgraded {upgraded} YouTube transcripts for {analyst.name}.")
    return upgraded


def collect_youtube_transcripts(analyst: "Analyst", db: Session) -> int:
    """Fetch recent YouTube video transcripts for analyst and store as Statements."""
    if not analyst.youtube_channel_id:
        logger.info(f"Analyst {analyst.name} has no YouTube channel ID, skipping.")
        return 0

    # Import here so missing package doesn't break the whole app
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
    except ImportError:
        logger.error("youtube-transcript-api not installed.")
        return 0

    channel_id = _resolve_channel_id(analyst.youtube_channel_id)
    if not channel_id:
        logger.error(f"Could not resolve YouTube channel ID from: {analyst.youtube_channel_id!r}")
        return 0

    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    logger.info(f"Fetching YouTube feed for {analyst.name}: {feed_url}")

    try:
        with httpx.Client(follow_redirects=True, timeout=15, headers=_YT_HEADERS) as client:
            response = client.get(feed_url)
            response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as exc:
        logger.error(f"Failed to fetch YouTube feed for {analyst.name}: {exc}")
        return 0

    new_count = 0
    for entry in feed.entries:
        video_url = entry.get("link", "")
        video_id = entry.get("yt_videoid", "")
        if not video_id:
            # Try to extract from URL
            if "v=" in video_url:
                video_id = video_url.split("v=")[-1].split("&")[0]
        if not video_id:
            continue

        title = entry.get("title", "")

        # Check duplicate
        existing = (
            db.query(Statement)
            .filter(Statement.analyst_id == analyst.id, Statement.source_url == video_url)
            .first()
        )
        if existing:
            continue

        published_at = None
        if entry.get("published_parsed"):
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        # Fetch transcript; try Whisper if API fails; fall back to RSS video description
        content = None
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            joined = " ".join(seg.get("text", "") for seg in transcript_list)
            if joined.strip():
                content = joined
        except Exception as exc:
            logger.info(f"Transcript unavailable for {video_id} ({exc}), trying Whisper.")

        if not content:
            try:
                from app.services.transcriber import transcribe_youtube
                whisper_content = transcribe_youtube(video_id)
                if whisper_content and len(whisper_content.strip()) > 50:
                    content = whisper_content
                    logger.info(f"Got Whisper transcript for video {video_id}")
            except Exception as exc:
                logger.debug(f"Whisper failed for {video_id}: {exc}")

        if not content:
            # Extract description from RSS entry (media:description field)
            raw_desc = ""
            for tag in entry.get("tags", []):
                pass  # tags aren't descriptions
            # feedparser exposes media:description as entry.media_description or via summary
            media_content = entry.get("media_content", [])
            if not raw_desc:
                raw_desc = entry.get("summary", "") or ""
            # Also try direct attribute feedparser may set
            if hasattr(entry, "media_description"):
                raw_desc = entry.media_description

            # Strip boilerplate that follows the actual description
            boilerplate_markers = [
                "Join the Patreon", "Where to find more", "Where to find me",
                "Subscribe to the Newsletter", "Full Newsletter:", "Full analysis available",
            ]
            lines = raw_desc.splitlines()
            clean_lines = []
            for line in lines:
                if any(marker in line for marker in boilerplate_markers):
                    break
                clean_lines.append(line)
            raw_desc = "\n".join(clean_lines).strip()

            if len(raw_desc) >= 80:
                content = f"[Video description] {raw_desc}"

        if not content:
            logger.info(f"No usable content for video {video_id}, skipping.")
            continue

        statement = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.youtube,
            source_url=video_url or f"https://www.youtube.com/watch?v={video_id}",
            source_title=title,
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
            logger.debug(f"Duplicate YouTube statement skipped: {video_url}")
        except Exception as exc:
            db.rollback()
            logger.error(f"Error saving YouTube statement for {video_id}: {exc}")

    logger.info(f"Collected {new_count} new YouTube transcripts for {analyst.name}.")
    return new_count
