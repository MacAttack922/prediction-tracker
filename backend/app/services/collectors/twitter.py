import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, List, Dict

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Statement, SourceType

if TYPE_CHECKING:
    from app.models import Analyst

logger = logging.getLogger(__name__)


def _get_tweets(handle: str, limit: int = 100) -> List[Dict]:
    """Fetch tweets using twscrape."""
    try:
        import twscrape
    except ImportError:
        logger.info("twscrape not installed — skipping Twitter collection.")
        return []

    async def _fetch():
        api = twscrape.API()
        users = await api.user_by_login(handle)
        if not users:
            logger.warning(f"Twitter user not found: {handle}")
            return []
        tweets = []
        async for tweet in api.user_tweets(users.id, limit=limit):
            tweets.append({
                "id": str(tweet.id),
                "url": tweet.url,
                "content": tweet.rawContent,
                "date": tweet.date,
            })
        return tweets

    try:
        return asyncio.run(_fetch())
    except Exception as exc:
        logger.error(f"Twitter fetch failed for @{handle}: {exc}")
        return []


def collect_tweets(analyst: "Analyst", db: Session) -> int:
    if not analyst.twitter_handle:
        return 0

    handle = analyst.twitter_handle.lstrip("@")
    logger.info(f"Fetching tweets for @{handle}")

    tweets = _get_tweets(handle)
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
        if hasattr(published_at, "replace"):
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

    logger.info(f"Collected {new_count} new tweets for @{handle}.")
    return new_count
