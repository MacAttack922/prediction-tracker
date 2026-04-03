import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Statement, SourceType

if TYPE_CHECKING:
    from app.models import Analyst

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _fetch_transcript_from_url(url: str) -> Optional[str]:
    """Try to fetch a transcript from a direct URL."""
    try:
        with httpx.Client(follow_redirects=True, timeout=10, headers=_HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
    except Exception as exc:
        logger.debug(f"Could not fetch transcript URL {url}: {exc}")
        return None

    # Plain text transcript
    content_type = r.headers.get("content-type", "")
    if "text/plain" in content_type:
        return r.text.strip() or None

    # HTML page — look for transcript block
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # Common transcript container patterns
    for selector in ["[class*='transcript']", "[id*='transcript']", "article", "main"]:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

    return None


def _get_episode_transcript(entry: dict) -> Optional[str]:
    """Try multiple strategies to get a transcript for a podcast episode."""

    # Strategy 1: Podcasting 2.0 <podcast:transcript> tag
    # feedparser exposes these under entry.podcast_transcript or tags
    transcript_url = None
    for tag in entry.get("tags", []):
        if "transcript" in tag.get("term", "").lower():
            transcript_url = tag.get("scheme") or tag.get("label")
            break

    # Also check for podcast_transcript attribute directly
    raw_transcript = getattr(entry, "podcast_transcript", None)
    if isinstance(raw_transcript, list) and raw_transcript:
        transcript_url = raw_transcript[0].get("url") or raw_transcript[0].get("href")
    elif isinstance(raw_transcript, dict):
        transcript_url = raw_transcript.get("url") or raw_transcript.get("href")

    if transcript_url:
        text = _fetch_transcript_from_url(transcript_url)
        if text:
            return text

    # Strategy 2: Look for a transcript link in the episode's show notes
    summary_html = entry.get("summary", "") or ""
    if summary_html:
        soup = BeautifulSoup(summary_html, "html.parser")
        for a in soup.find_all("a", href=True):
            if "transcript" in (a.get_text() + a["href"]).lower():
                text = _fetch_transcript_from_url(a["href"])
                if text:
                    return text

    # Strategy 3: Fall back to the episode page itself
    episode_url = entry.get("link", "")
    if episode_url:
        text = _fetch_transcript_from_url(episode_url)
        if text and len(text) > 300:
            return text

    return None


def collect_podcast_episodes(analyst: "Analyst", db: Session) -> int:
    """Fetch podcast RSS feed and collect episode transcripts or descriptions."""
    if not analyst.podcast_rss_url:
        return 0

    logger.info(f"Fetching podcast feed for {analyst.name}: {analyst.podcast_rss_url}")

    try:
        with httpx.Client(follow_redirects=True, timeout=15, headers=_HEADERS) as client:
            r = client.get(analyst.podcast_rss_url)
            r.raise_for_status()
        feed = feedparser.parse(r.content)
    except Exception as exc:
        logger.error(f"Failed to fetch podcast feed for {analyst.name}: {exc}")
        return 0

    new_count = 0
    for entry in feed.entries:
        url = entry.get("link", "") or entry.get("id", "")
        if not url:
            continue

        existing = (
            db.query(Statement)
            .filter(Statement.analyst_id == analyst.id, Statement.source_url == url)
            .first()
        )
        if existing:
            continue

        title = entry.get("title", "")

        published_at = None
        if entry.get("published_parsed"):
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        # Try to get a transcript; try Whisper via audio enclosure; fall back to show notes
        content = _get_episode_transcript(entry)
        if not content or len(content.strip()) < 100:
            # Look for audio enclosure to transcribe with Whisper
            enclosures = entry.get("enclosures", [])
            audio_url = None
            for enc in enclosures:
                enc_type = enc.get("type", "") or ""
                if enc_type.startswith("audio"):
                    audio_url = enc.get("url") or enc.get("href")
                    break
            if audio_url:
                try:
                    from app.services.transcriber import transcribe_url
                    whisper_content = transcribe_url(audio_url)
                    if whisper_content and len(whisper_content.strip()) > 100:
                        content = whisper_content
                        logger.info(f"Got Whisper transcript for podcast episode: {title}")
                except Exception as exc:
                    logger.debug(f"Whisper transcription failed for {audio_url}: {exc}")

        if not content:
            raw = entry.get("summary", "") or entry.get("description", "") or ""
            if raw:
                content = BeautifulSoup(raw, "html.parser").get_text(separator="\n", strip=True)

        if not content or len(content.strip()) < 80:
            logger.debug(f"No usable content for podcast episode: {title}")
            continue

        statement = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.podcast,
            source_url=url,
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
        except Exception as exc:
            db.rollback()
            logger.error(f"Error saving podcast episode {url}: {exc}")

    logger.info(f"Collected {new_count} new podcast episodes for {analyst.name}.")
    return new_count
