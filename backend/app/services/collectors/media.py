"""
Collectors for major TV/media network transcripts and articles:
Fox News, Bloomberg — found via Google News RSS, scraped for full text.
"""
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
    try:
        with httpx.Client(follow_redirects=True, timeout=12, headers=_HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
    except Exception as exc:
        logger.debug(f"Could not fetch {url}: {exc}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    # Try network-specific selectors first, then generic fallbacks
    selectors = [
        # Fox News
        "div.article-body", "div[class*='article-content']",
        # Bloomberg
        "div.body-content", "div[class*='body__content']", "article.article-wrap",
        # Generic
        "article", "main", "div[class*='content']",
    ]
    for sel in selectors:
        try:
            container = soup.select_one(sel)
        except Exception:
            continue
        if container:
            paragraphs = [p.get_text(separator=" ", strip=True) for p in container.find_all("p")]
            text = "\n\n".join(p for p in paragraphs if len(p) > 40)
            if len(text) > 150:
                return text

    # Last resort: all <p> tags
    paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
    text = "\n\n".join(p for p in paragraphs if len(p) > 40)
    return text if len(text) > 150 else None


def _time_windows(start_year: int = 2010) -> list:
    from datetime import date
    windows = []
    year = start_year
    current_year = date.today().year
    while year <= current_year:
        end = min(year + 3, current_year + 1)
        windows.append((f"{year}-01-01", f"{end}-01-01"))
        year = end
    return windows


def _fetch_and_save(analyst: "Analyst", db: Session, query: str, source_type: SourceType, seen_urls: set) -> int:
    feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        return 0

    new_count = 0
    for entry in feed.entries:
        url = entry.get("link", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        existing = db.query(Statement).filter(
            Statement.analyst_id == analyst.id,
            Statement.source_url == url,
        ).first()
        if existing:
            continue

        title = entry.get("title", "")
        content = _fetch_article_text(url)
        if not content:
            raw = entry.get("summary", "") or ""
            content = BeautifulSoup(raw, "html.parser").get_text(separator=" ", strip=True) if raw else title
        if len(content.strip()) < 80:
            continue

        published_at = None
        if entry.get("published_parsed"):
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        stmt = Statement(
            analyst_id=analyst.id,
            source_type=source_type,
            source_url=url,
            source_title=title,
            content=content,
            published_at=published_at,
            is_processed=False,
        )
        try:
            db.add(stmt)
            db.commit()
            new_count += 1
        except IntegrityError:
            db.rollback()
        except Exception as exc:
            db.rollback()
            logger.error(f"Error saving statement for {url}: {exc}")

    return new_count


def _collect_for_network(
    analyst: "Analyst",
    db: Session,
    site: str,
    source_type: SourceType,
) -> int:
    """Search Google News RSS for a specific network, sweeping time windows back to 2010."""
    seen_urls: set = set()
    new_count = 0
    name = analyst.name

    # Recent (no date filter)
    new_count += _fetch_and_save(analyst, db, f'site:{site} "{name}"', source_type, seen_urls)

    # Historical windows back to 2010
    for after, before in _time_windows(start_year=2010):
        query = f'site:{site} "{name}" after:{after} before:{before}'
        new_count += _fetch_and_save(analyst, db, query, source_type, seen_urls)

    return new_count


def collect_media_mentions(analyst: "Analyst", db: Session) -> int:
    """Collect Fox News and Bloomberg mentions for an analyst."""
    fox_new = _collect_for_network(analyst, db, "foxnews.com", SourceType.fox_news)
    bloomberg_new = _collect_for_network(analyst, db, "bloomberg.com", SourceType.bloomberg)
    total = fox_new + bloomberg_new
    logger.info(
        f"Media mentions for {analyst.name}: {fox_new} Fox News, {bloomberg_new} Bloomberg"
    )
    return total
