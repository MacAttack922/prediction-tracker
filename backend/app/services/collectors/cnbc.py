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
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _fetch_cnbc_transcript(url: str) -> Optional[str]:
    try:
        with httpx.Client(follow_redirects=True, timeout=10, headers=_HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
    except Exception as exc:
        logger.debug(f"Could not fetch CNBC page {url}: {exc}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # CNBC transcript content selectors
    for selector in [
        "div.ArticleBody-articleBody",
        "div[class*='ArticleBody']",
        "div[class*='article-body']",
        "article",
        "main",
    ]:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator="\n", strip=True)
            if len(text) > 300:
                return text

    return None


def collect_cnbc_transcripts(analyst: "Analyst", db: Session) -> int:
    query = quote_plus(f'site:cnbc.com/transcripts "{analyst.name}"')
    feed_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.error(f"CNBC search failed for {analyst.name}: {exc}")
        return 0

    new_count = 0
    for entry in feed.entries:
        url = entry.get("link", "")
        if not url or "cnbc.com" not in url:
            continue

        existing = (
            db.query(Statement)
            .filter(Statement.analyst_id == analyst.id, Statement.source_url == url)
            .first()
        )
        if existing:
            continue

        title = entry.get("title", "")

        content = _fetch_cnbc_transcript(url)
        if not content or len(content) < 200:
            continue

        published_at = None
        if entry.get("published_parsed"):
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        statement = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.cnbc,
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
            logger.error(f"Error saving CNBC statement {url}: {exc}")

    logger.info(f"Collected {new_count} CNBC transcripts for {analyst.name}.")
    return new_count
