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


def _fetch_feed_entries(query: str) -> list:
    """Fetch entries from a single Google News RSS query."""
    feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(feed_url)
        return feed.entries or []
    except Exception as exc:
        logger.debug(f"Google News feed failed for query '{query}': {exc}")
        return []


def _save_entry(analyst_id: int, entry: dict, db: Session) -> bool:
    """Save a single feed entry as a Statement. Returns True if newly saved."""
    url = entry.get("link", "")
    if not url:
        return False
    existing = db.query(Statement).filter(
        Statement.analyst_id == analyst_id, Statement.source_url == url
    ).first()
    if existing:
        return False

    title = entry.get("title", "")
    full_text = _fetch_article_text(url)
    if full_text:
        content = full_text
    else:
        raw = entry.get("summary", "") or ""
        content = BeautifulSoup(raw, "html.parser").get_text(separator=" ", strip=True) if raw else title

    if len(content.strip()) < 80:
        return False

    published_at = None
    if entry.get("published_parsed"):
        try:
            published_at = datetime(*entry.published_parsed[:6])
        except Exception:
            pass

    statement = Statement(
        analyst_id=analyst_id,
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
        return True
    except IntegrityError:
        db.rollback()
        return False
    except Exception as exc:
        db.rollback()
        logger.error(f"Error saving Google News statement for {url}: {exc}")
        return False


def _time_windows(start_year: int = 2010) -> list:
    """Generate 3-year date windows from start_year to today."""
    from datetime import date
    windows = []
    year = start_year
    current_year = date.today().year
    while year <= current_year:
        end = min(year + 3, current_year + 1)
        windows.append((f"{year}-01-01", f"{end}-01-01"))
        year = end
    return windows


def collect_news_mentions(analyst: "Analyst", db: Session) -> int:
    """Search Google News RSS across multiple queries AND time windows back to 2010."""
    name = analyst.name

    # Current/recent queries (no date filter — picks up latest)
    recent_queries = [
        name,
        f'"{name}" prediction',
        f'"{name}" forecast',
        f'"{name}" interview',
        f'"{name}" says',
    ]

    # Historical queries: sweep time windows back to 2010
    historical_queries = []
    for after, before in _time_windows(start_year=2010):
        historical_queries.append(f'"{name}" after:{after} before:{before}')
        historical_queries.append(f'"{name}" prediction after:{after} before:{before}')

    seen_urls: set = set()
    new_count = 0

    for query in recent_queries + historical_queries:
        entries = _fetch_feed_entries(query)
        for entry in entries:
            url = entry.get("link", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            if _save_entry(analyst.id, entry, db):
                new_count += 1

    logger.info(f"Collected {new_count} new Google News mentions for {analyst.name}.")
    return new_count
