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


def _fetch_full_post(url: str) -> Optional[str]:
    """Attempt to fetch the full Substack post HTML and extract readable text."""
    try:
        with httpx.Client(follow_redirects=True, timeout=12, headers=_HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
    except Exception as exc:
        logger.debug(f"Could not fetch full post {url}: {exc}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # Substack content selectors (most specific first)
    for selector in [
        "div.available-content",
        "div[class*='body']",
        "div[class*='post-content']",
        "div[class*='markup']",
        "article",
        "main",
    ]:
        try:
            container = soup.select_one(selector)
        except Exception:
            continue
        if container:
            text = container.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

    # Fallback: collect all <p> tags from body
    paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
    text = "\n\n".join(p for p in paragraphs if len(p) > 40)
    return text if len(text) > 200 else None


def collect_substack_posts(analyst: "Analyst", db: Session) -> int:
    """Fetch RSS feed from analyst's Substack and store new posts as Statements."""
    if not analyst.substack_url:
        logger.info(f"Analyst {analyst.name} has no Substack URL, skipping.")
        return 0

    feed_url = analyst.substack_url.rstrip("/") + "/feed"
    logger.info(f"Fetching Substack feed for {analyst.name}: {feed_url}")

    try:
        feed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.error(f"Failed to fetch Substack feed for {analyst.name}: {exc}")
        return 0

    if feed.bozo and feed.bozo_exception:
        logger.warning(f"Feed parse warning for {analyst.name}: {feed.bozo_exception}")

    new_count = 0
    for entry in feed.entries:
        url = entry.get("link", "")
        if not url:
            continue

        # Check if we already have this URL
        existing = (
            db.query(Statement)
            .filter(Statement.analyst_id == analyst.id, Statement.source_url == url)
            .first()
        )
        if existing:
            continue

        title = entry.get("title", "")

        # First try to fetch the full article HTML from the post URL
        content = _fetch_full_post(url)

        # Fall back to RSS content/summary if full fetch failed or returned nothing
        if not content:
            raw_html = ""
            if entry.get("content"):
                raw_html = entry["content"][0].get("value", "")
            if not raw_html:
                raw_html = entry.get("summary", "")
            if raw_html:
                soup = BeautifulSoup(raw_html, "html.parser")
                content = soup.get_text(separator="\n", strip=True)
            else:
                content = title

        published_at = None
        if entry.get("published_parsed"):
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        statement = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.substack,
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
            logger.debug(f"Duplicate statement skipped: {url}")
        except Exception as exc:
            db.rollback()
            logger.error(f"Error saving statement for {url}: {exc}")

    logger.info(f"Collected {new_count} new Substack posts for {analyst.name}.")
    return new_count
