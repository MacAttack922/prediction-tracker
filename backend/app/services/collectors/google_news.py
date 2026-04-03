import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote_plus

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
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _fetch_article_text(url: str) -> Optional[str]:
    """Follow redirects and extract readable text from an article URL."""
    try:
        with httpx.Client(follow_redirects=True, timeout=10, headers=_HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
    except Exception as exc:
        logger.debug(f"Could not fetch article {url}: {exc}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove boilerplate tags
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    # Prefer <article> tag, then <main>, then fall back to full body
    container = soup.find("article") or soup.find("main") or soup.find("body")
    if not container:
        return None

    paragraphs = [p.get_text(separator=" ", strip=True) for p in container.find_all("p")]
    text = "\n\n".join(p for p in paragraphs if len(p) > 40)
    return text if len(text) > 100 else None


def collect_news_mentions(analyst: "Analyst", db: Session) -> int:
    """Search Google News RSS for mentions of the analyst and store as Statements."""
    query = quote_plus(analyst.name)
    feed_url = (
        f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    )
    logger.info(f"Fetching Google News for {analyst.name}: {feed_url}")

    try:
        feed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.error(f"Failed to fetch Google News for {analyst.name}: {exc}")
        return 0

    if feed.bozo and feed.bozo_exception:
        logger.warning(f"Feed parse warning for {analyst.name}: {feed.bozo_exception}")

    new_count = 0
    for entry in feed.entries:
        url = entry.get("link", "")
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
        # Try to fetch the full article; fall back to RSS summary stripped of HTML
        full_text = _fetch_article_text(url)
        if full_text:
            content = full_text
        else:
            raw = entry.get("summary", "") or ""
            content = BeautifulSoup(raw, "html.parser").get_text(separator=" ", strip=True) if raw else title

        # Skip entries with no real content beyond the title
        if len(content.strip()) < 80:
            continue

        published_at = None
        if entry.get("published_parsed"):
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        statement = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.google_news,
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
            logger.error(f"Error saving Google News statement for {url}: {exc}")

    logger.info(f"Collected {new_count} new Google News mentions for {analyst.name}.")
    return new_count
