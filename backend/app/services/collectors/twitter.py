import logging
import json
from datetime import datetime
from typing import TYPE_CHECKING, List, Dict, Optional
from urllib.parse import quote_plus

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

# Nitter instances to try in order
_NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
]


def _fetch_nitter_timeline(handle: str) -> List[Dict]:
    """Try each Nitter instance to fetch recent tweets."""
    for base in _NITTER_INSTANCES:
        url = f"{base}/{handle}"
        try:
            with httpx.Client(follow_redirects=True, timeout=10, headers=_HEADERS) as client:
                r = client.get(url)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            tweets = []
            for item in soup.select(".timeline-item"):
                text_el = item.select_one(".tweet-content")
                link_el = item.select_one("a.tweet-link")
                date_el = item.select_one(".tweet-date a")
                if not text_el or not link_el:
                    continue
                content = text_el.get_text(separator=" ", strip=True)
                tweet_path = link_el.get("href", "")
                tweet_url = f"https://x.com{tweet_path}" if tweet_path.startswith("/") else tweet_path
                published_at = None
                if date_el and date_el.get("title"):
                    try:
                        published_at = datetime.strptime(date_el["title"], "%b %d, %Y · %I:%M %p %Z")
                    except Exception:
                        pass
                tweets.append({"url": tweet_url, "content": content, "date": published_at})
            if tweets:
                logger.info(f"Nitter: {len(tweets)} tweets from {base} for @{handle}")
                return tweets
        except Exception as exc:
            logger.debug(f"Nitter {base} failed for @{handle}: {exc}")
    return []


def _fetch_wayback_tweets(handle: str) -> List[Dict]:
    """
    Query the Wayback Machine CDX API for archived tweets from a user,
    going back to 2010. Fetches the archived page for each tweet to extract text.
    """
    cdx_url = (
        "https://web.archive.org/cdx/search/cdx"
        f"?url=twitter.com/{handle}/status/*"
        "&output=json&limit=1000"
        "&fl=original,timestamp"
        "&collapse=urlkey"
        "&filter=statuscode:200"
        "&from=20100101"
    )
    try:
        with httpx.Client(timeout=20, headers=_HEADERS) as client:
            r = client.get(cdx_url)
        if r.status_code != 200:
            logger.debug(f"Wayback CDX returned {r.status_code} for @{handle}")
            return []
        rows = r.json()
    except Exception as exc:
        logger.debug(f"Wayback CDX failed for @{handle}: {exc}")
        return []

    if not rows or len(rows) < 2:
        return []

    # First row is header ["original", "timestamp"]
    results = []
    for original, timestamp in rows[1:]:
        archive_url = f"https://web.archive.org/web/{timestamp}/{original}"
        tweet_id = original.rstrip("/").split("/")[-1].split("?")[0]
        canonical_url = f"https://x.com/{handle}/status/{tweet_id}"

        # Parse date from timestamp (format: YYYYMMDDHHMMSS)
        published_at = None
        try:
            published_at = datetime.strptime(timestamp[:8], "%Y%m%d")
        except Exception:
            pass

        # Fetch archived tweet page
        content = None
        try:
            with httpx.Client(follow_redirects=True, timeout=12, headers=_HEADERS) as client:
                r = client.get(archive_url)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                # Try Twitter's old and new markup
                for sel in [
                    "div.tweet-text", "div[data-testid='tweetText']",
                    "p.TweetTextSize", "div.js-tweet-text-container",
                ]:
                    el = soup.select_one(sel)
                    if el:
                        content = el.get_text(separator=" ", strip=True)
                        break
        except Exception as exc:
            logger.debug(f"Wayback fetch failed for {archive_url}: {exc}")

        if content and len(content) > 20:
            results.append({
                "url": canonical_url,
                "content": content,
                "date": published_at,
            })

    logger.info(f"Wayback Machine: found {len(results)} tweets for @{handle}")
    return results


def _fetch_google_tweets(name: str, handle: Optional[str]) -> List[Dict]:
    """Search Google News RSS for site:x.com mentions."""
    import feedparser
    if handle:
        q = quote_plus(f'site:x.com/{handle}')
    else:
        q = quote_plus(f'site:x.com "{name}"')
    feed_url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        return []

    results = []
    for entry in feed.entries:
        url = entry.get("link", "")
        if not url or "x.com" not in url:
            continue
        title = entry.get("title", "")
        raw = entry.get("summary", "") or ""
        content = BeautifulSoup(raw, "html.parser").get_text(separator=" ", strip=True) if raw else title
        if not content or len(content) < 30:
            content = title
        published_at = None
        if entry.get("published_parsed"):
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception:
                pass
        results.append({"url": url, "content": content, "date": published_at})
    return results


def collect_tweets(analyst: "Analyst", db: Session) -> int:
    handle = analyst.twitter_handle.lstrip("@") if analyst.twitter_handle else None

    # Collect from all sources: Nitter (recent), Wayback Machine (historical), Google
    all_tweets: List[Dict] = []

    if handle:
        all_tweets.extend(_fetch_nitter_timeline(handle))
        all_tweets.extend(_fetch_wayback_tweets(handle))

    if not all_tweets:
        all_tweets.extend(_fetch_google_tweets(analyst.name, handle))

    if not all_tweets:
        return 0

    # Deduplicate by URL
    seen_urls: set = set()
    new_count = 0

    for tweet in all_tweets:
        url = tweet.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        existing = db.query(Statement).filter(
            Statement.analyst_id == analyst.id,
            Statement.source_url == url,
        ).first()
        if existing:
            continue

        content = tweet.get("content", "").strip()
        if len(content) < 30:
            continue

        published_at = tweet.get("date")
        if hasattr(published_at, "replace") and getattr(published_at, "tzinfo", None) is not None:
            published_at = published_at.replace(tzinfo=None)

        statement = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.twitter,
            source_url=url,
            source_title=None,
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
            logger.error(f"Error saving tweet {url}: {exc}")

    logger.info(f"Collected {new_count} new tweets for {analyst.name}.")
    return new_count
