import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from urllib.parse import urljoin, urlparse

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

_COMMON_FEED_PATHS = [
    "/feed", "/feed.xml", "/rss", "/rss.xml", "/atom.xml",
    "/blog/feed", "/blog/rss", "/index.xml", "/feeds/posts/default",
]


def _discover_feed_url(base_url: str) -> Optional[str]:
    """Try to find an RSS/Atom feed for the given website."""
    try:
        with httpx.Client(follow_redirects=True, timeout=10, headers=_HEADERS) as client:
            r = client.get(base_url)
        soup = BeautifulSoup(r.text, "html.parser")
        # Check HTML <link rel="alternate"> tags
        for link in soup.find_all("link", rel="alternate"):
            t = link.get("type", "")
            if "rss" in t or "atom" in t:
                href = link.get("href", "")
                if href:
                    return urljoin(base_url, href)
    except Exception as exc:
        logger.debug(f"Homepage fetch failed for {base_url}: {exc}")

    # Probe common paths
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    for path in _COMMON_FEED_PATHS:
        url = origin + path
        try:
            with httpx.Client(follow_redirects=True, timeout=8, headers=_HEADERS) as client:
                r = client.get(url)
            if r.status_code == 200 and (
                "xml" in r.headers.get("content-type", "") or
                r.text.strip().startswith("<?xml") or
                "<rss" in r.text[:500] or
                "<feed" in r.text[:500]
            ):
                return url
        except Exception:
            pass

    return None


def _fetch_sitemap_urls(base_url: str) -> List[str]:
    """Extract post URLs from sitemap.xml (or sitemap index)."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    sitemap_url = origin + "/sitemap.xml"
    urls = []
    try:
        with httpx.Client(follow_redirects=True, timeout=10, headers=_HEADERS) as client:
            r = client.get(sitemap_url)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "xml")
        # Sitemap index — recurse one level
        for sitemap in soup.find_all("sitemap"):
            loc = sitemap.find("loc")
            if not loc:
                continue
            child_url = loc.text.strip()
            # Only follow post/article sitemaps, skip image/video
            if any(x in child_url for x in ["post", "article", "blog", "page"]):
                try:
                    with httpx.Client(follow_redirects=True, timeout=10, headers=_HEADERS) as client:
                        r2 = client.get(child_url)
                    s2 = BeautifulSoup(r2.text, "xml")
                    for url_tag in s2.find_all("url"):
                        loc2 = url_tag.find("loc")
                        if loc2:
                            urls.append(loc2.text.strip())
                except Exception:
                    pass
        # Direct sitemap
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if loc:
                urls.append(loc.text.strip())
    except Exception as exc:
        logger.debug(f"Sitemap fetch failed for {base_url}: {exc}")
    return urls


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
    container = (
        soup.find("article") or
        soup.find("div", class_=lambda c: c and any(x in c for x in ["post-content", "entry-content", "article-body", "blog-content"])) or
        soup.find("main") or
        soup.find("body")
    )
    if not container:
        return None
    paragraphs = [p.get_text(separator=" ", strip=True) for p in container.find_all("p")]
    text = "\n\n".join(p for p in paragraphs if len(p) > 40)
    return text if len(text) > 150 else None


def collect_website_posts(analyst: "Analyst", db: Session) -> int:
    """Scrape analyst's personal website: try RSS feed first, fall back to sitemap crawl."""
    if not analyst.website_url:
        return 0

    base_url = analyst.website_url.rstrip("/")
    new_count = 0

    # --- Strategy 1: RSS/Atom feed ---
    feed_url = _discover_feed_url(base_url)
    if feed_url:
        logger.info(f"Found feed for {analyst.name}: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
        except Exception as exc:
            logger.error(f"Failed to parse feed {feed_url}: {exc}")
            feed = None

        if feed and feed.entries:
            for entry in feed.entries:
                url = entry.get("link", "")
                if not url:
                    continue
                existing = db.query(Statement).filter(
                    Statement.analyst_id == analyst.id,
                    Statement.source_url == url
                ).first()
                if existing:
                    continue

                title = entry.get("title", "")
                content = _fetch_article_text(url)
                if not content:
                    raw = entry.get("content", [{}])[0].get("value", "") or entry.get("summary", "")
                    if raw:
                        content = BeautifulSoup(raw, "html.parser").get_text(separator="\n", strip=True)
                if not content or len(content) < 80:
                    continue

                published_at = None
                if entry.get("published_parsed"):
                    try:
                        published_at = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass

                stmt = Statement(
                    analyst_id=analyst.id,
                    source_type=SourceType.website,
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
                    logger.error(f"Error saving website post {url}: {exc}")

            logger.info(f"Collected {new_count} posts via RSS for {analyst.name}")
            return new_count

    # --- Strategy 2: Sitemap crawl ---
    logger.info(f"No RSS found for {analyst.name}, trying sitemap")
    urls = _fetch_sitemap_urls(base_url)
    # Filter to likely blog/article URLs; skip navigation/meta pages
    skip_patterns = [
        "/tag/", "/category/", "/author/", "/page/", "/archive/",
        "/about", "/contact", "/privacy", "/terms", "/subscribe",
        "/search", "/feed", "/rss", "?", "#",
    ]
    article_urls = [u for u in urls if not any(p in u for p in skip_patterns)]
    logger.info(f"Sitemap yielded {len(article_urls)} candidate URLs for {analyst.name}")

    for url in article_urls:
        existing = db.query(Statement).filter(
            Statement.analyst_id == analyst.id,
            Statement.source_url == url
        ).first()
        if existing:
            continue
        content = _fetch_article_text(url)
        if not content:
            continue
        stmt = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.website,
            source_url=url,
            source_title=None,
            content=content,
            published_at=None,
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
            logger.error(f"Error saving website page {url}: {exc}")

    logger.info(f"Collected {new_count} new website posts for {analyst.name}.")
    return new_count
