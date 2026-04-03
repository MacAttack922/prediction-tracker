import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Statement, SourceType

if TYPE_CHECKING:
    from app.models import Analyst

logger = logging.getLogger(__name__)

LISTENNOTES_API_BASE = "https://listen-api.listennotes.com/api/v2"


def collect_podcast_guest_appearances(analyst: "Analyst", db: Session) -> int:
    """Search Listen Notes for podcast episodes featuring the analyst as a guest."""
    api_key = os.getenv("LISTENNOTES_API_KEY")
    if not api_key:
        logger.info("LISTENNOTES_API_KEY not set — skipping Listen Notes search.")
        return 0

    params = {
        "q": analyst.name,
        "type": "episode",
        "language": "English",
        "sort_by_date": 1,
        "safe_mode": 0,
    }
    headers = {
        "X-ListenAPI-Key": api_key,
        "User-Agent": "prediction-tracker/1.0",
    }

    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(f"{LISTENNOTES_API_BASE}/search", params=params, headers=headers)
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.error(f"Listen Notes API failed for {analyst.name}: {exc}")
        return 0

    new_count = 0
    for result in data.get("results", []):
        episode_id = result.get("id", "")
        episode_url = result.get("listennotes_url") or f"https://www.listennotes.com/e/{episode_id}"
        title = result.get("title_original", "")
        podcast_info = result.get("podcast") or {}
        podcast_title = podcast_info.get("title_original", "")

        existing = (
            db.query(Statement)
            .filter(Statement.analyst_id == analyst.id, Statement.source_url == episode_url)
            .first()
        )
        if existing:
            continue

        published_at = None
        pub_ms = result.get("pub_date_ms")
        if pub_ms:
            try:
                published_at = datetime.utcfromtimestamp(pub_ms / 1000)
            except Exception:
                pass

        raw_desc = result.get("description_original", "") or ""
        if raw_desc:
            content = BeautifulSoup(raw_desc, "html.parser").get_text(separator="\n", strip=True)
        else:
            content = title

        if len(content.strip()) < 80:
            logger.debug(f"Episode too short to process: {title}")
            continue

        display_title = f"{podcast_title}: {title}" if podcast_title else title

        statement = Statement(
            analyst_id=analyst.id,
            source_type=SourceType.podcast_guest,
            source_url=episode_url,
            source_title=display_title,
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
            logger.debug(f"Duplicate podcast guest statement skipped: {episode_url}")
        except Exception as exc:
            db.rollback()
            logger.error(f"Error saving podcast guest statement {episode_url}: {exc}")

    logger.info(f"Collected {new_count} new podcast guest appearances for {analyst.name}.")
    return new_count
