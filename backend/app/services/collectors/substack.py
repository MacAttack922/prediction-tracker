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
    """Fetch a Substack post HTML and extract as much text as possible, including paywalled previews."""
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

    # Remove the paywall subscription box but keep text above it
    for el in soup.select("div.paywall, div[class*='paywall'], div.subscribe-widget, div[class*='subscribe']"):
        el.decompose()

    # Substack content selectors — ordered from most to least specific
    for selector in [
        "div.available-content",
        "div.body.markup",
        "div[class*='post-content']",
        "div[class*='markup']",
        "div[class*='body']",
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


def _fetch_all_substack_posts(base_url: str) -> list:
    """Use Substack's API to paginate through ALL posts (full history)."""
    api_base = base_url.rstrip("/")
    posts = []
    offset = 0
    limit = 50
    while True:
        try:
            with httpx.Client(follow_redirects=True, timeout=15, headers=_HEADERS) as client:
                r = client.get(f"{api_base}/api/v1/posts?limit={limit}&offset={offset}")
            if r.status_code != 200:
                break
            batch = r.json()
        except Exception as exc:
            logger.debug(f"Substack API pagination failed at offset {offset}: {exc}")
            break
        if not batch:
            break
        posts.extend(batch)
        if len(batch) < limit:
            break  # last page
        offset += limit
    logger.info(f"Substack API returned {len(posts)} total posts for {base_url}")
    return posts


def collect_substack_posts(analyst: "Analyst", db: Session) -> int:
    """Fetch ALL Substack posts (full history) and store as Statements."""
    if not analyst.substack_url:
        logger.info(f"Analyst {analyst.name} has no Substack URL, skipping.")
        return 0

    base_url = analyst.substack_url.rstrip("/")

    # Try paginated API first (full history); fall back to RSS (last ~20 posts)
    api_posts = _fetch_all_substack_posts(base_url)

    new_count = 0

    if api_posts:
        for post in api_posts:
            url = post.get("canonical_url") or post.get("url") or ""
            if not url:
                continue

            existing = (
                db.query(Statement)
                .filter(Statement.analyst_id == analyst.id, Statement.source_url == url)
                .first()
            )
            if existing:
                continue

            title = post.get("title", "")
            content = _fetch_full_post(url)

            if not content:
                # Use whatever the API provides — full body, preview, or truncated text
                body_html = (
                    post.get("body_html") or
                    post.get("preview_html") or
                    post.get("truncated_body_text") or
                    ""
                )
                if body_html:
                    soup = BeautifulSoup(body_html, "html.parser")
                    content = soup.get_text(separator="\n", strip=True)
                # Also append subtitle if present — often contains the key thesis
                subtitle = post.get("subtitle", "") or ""
                if subtitle and subtitle not in (content or ""):
                    content = (subtitle + "\n\n" + (content or "")).strip()
                if not content:
                    content = title

            published_at = None
            post_date = post.get("post_date") or post.get("published_at")
            if post_date:
                try:
                    published_at = datetime.fromisoformat(post_date.replace("Z", "+00:00")).replace(tzinfo=None)
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
            except Exception as exc:
                db.rollback()
                logger.error(f"Error saving Substack post {url}: {exc}")
    else:
        # Fallback: RSS feed (last ~20 posts only)
        logger.info(f"Falling back to RSS for {analyst.name}")
        feed_url = base_url + "/feed"
        try:
            feed = feedparser.parse(feed_url)
        except Exception as exc:
            logger.error(f"Failed to fetch Substack feed for {analyst.name}: {exc}")
            return 0

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
            content = _fetch_full_post(url)
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
            except Exception as exc:
                db.rollback()
                logger.error(f"Error saving Substack post {url}: {exc}")

    logger.info(f"Collected {new_count} new Substack posts for {analyst.name}.")
    return new_count
