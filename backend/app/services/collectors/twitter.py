import logging
from datetime import datetime
from typing import TYPE_CHECKING, List, Dict, Optional
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

# Nitter instances to try in order — these are community mirrors of Twitter
_NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
]


def _fetch_nitter_timeline(handle: str) -> List[Dict]:
    """Try each Nitter instance to fetch a user's recent tweets."""
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
                logger.info(f"Fetched {len(tweets)} tweets from {base} for @{handle}")
                return tweets
        except Exception as exc:
            logger.debug(f"Nitter instance {base} failed for @{handle}: {exc}")
    return []


def _fetch_google_tweets(name: str, handle: Optional[str]) -> List[Dict]:
    """Search Google News RSS for site:x.com mentions."""
    # Search by handle if available, otherwise by name
    if handle:
        q = quote_plus(f'site:x.com/{handle}')
    else:
        q = quote_plus(f'site:x.com "{name}"')

    feed_url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.debug(f"Google tweet search failed for {name}: {exc}")
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

    logger.info(f"Google tweet search found {len(results)} results for {name}")
    return results


def collect_tweets(analyst: "Analyst", db: Session) -> int:
    handle = analyst.twitter_handle.lstrip("@") if analyst.twitter_handle else None

    # Try Nitter first (full tweet text), fall back to Google News search
    tweets: List[Dict] = []
    if handle:
        tweets = _fetch_nitter_timeline(handle)
    if not tweets:
        tweets = _fetch_google_tweets(analyst.name, handle)

    if not tweets:
        logger.info(f"No tweets found for {analyst.name}")
        return 0

    new_count = 0
    for tweet in tweets:
        url = tweet.get("url", "")
        if not url:
            continue

        existing = (
            db.query(Statement)
            .filter(Statement.analyst_id == analyst.id, Statement.source_url == url)
            .first()
        )
        if existing:
            continue

        content = tweet.get("content", "").strip()
        if len(content) < 30:
            continue

        published_at = tweet.get("date")
        if hasattr(published_at, "replace") and published_at.tzinfo is not None:
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
