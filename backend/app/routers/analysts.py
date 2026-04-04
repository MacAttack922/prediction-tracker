import json
import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from urllib.parse import quote

import anthropic
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from app.database import get_db, SessionLocal
from app.models import Analyst, Statement, Prediction, PredictionOutcome
from app.schemas import (
    AnalystCreate, AnalystOut, AnalystDetail, AnalystScore,
    CollectResult, ProcessResult, JudgeResult,
)
from app.services.collectors.substack import collect_substack_posts
from app.services.collectors.google_news import collect_news_mentions
from app.services.collectors.youtube import collect_youtube_transcripts, retry_youtube_transcripts
from app.services.collectors.podcast import collect_podcast_episodes
from app.services.collectors.youtube_search import collect_youtube_guest_appearances
from app.services.collectors.listennotes import collect_podcast_guest_appearances
from app.services.collectors.twitter import collect_tweets
from app.services.collectors.cnbc import collect_cnbc_transcripts
from app.services.collectors.website import collect_website_posts
from app.services.collectors.media import collect_media_mentions
from app.services.llm.extractor import extract_predictions
from app.services.llm.judge import judge_prediction
from app.services.llm.summarizer import generate_analyst_summary
from app.services.scorer import compute_analyst_score

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysts", tags=["analysts"])


class AnalystUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    substack_url: Optional[str] = None
    youtube_channel_id: Optional[str] = None
    website_url: Optional[str] = None
    podcast_rss_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    profile_image_url: Optional[str] = None
    is_public: Optional[bool] = None


def _fetch_wikipedia_image(title: str) -> Optional[str]:
    """Fetch a profile photo from Wikipedia given an exact article title."""
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    try:
        with httpx.Client(follow_redirects=True, timeout=8) as client:
            r = client.get(url, headers={"User-Agent": "prediction-tracker/1.0"})
        if r.status_code == 200:
            data = r.json()
            return (data.get("thumbnail") or data.get("originalimage") or {}).get("source")
    except Exception as exc:
        logger.debug(f"Wikipedia image fetch failed for {title!r}: {exc}")
    return None


def _fetch_photo_via_llm(name: str, anthropic_client: "anthropic.Anthropic") -> Optional[str]:
    """Use Claude Haiku to resolve the exact Wikipedia article title, then fetch the photo."""
    try:
        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": (
                    f'What is the exact Wikipedia article title for the public figure named "{name}"? '
                    f'Reply with only the article title (e.g. "Ray Kurzweil"), or "null" if they do not have a Wikipedia page.'
                ),
            }],
        )
        wiki_title = response.content[0].text.strip().strip('"\'')
        if not wiki_title or wiki_title.lower() == "null":
            return None
        return _fetch_wikipedia_image(wiki_title)
    except Exception as exc:
        logger.debug(f"LLM photo lookup failed for {name!r}: {exc}")
    return None


def _get_anthropic_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def _make_unique_slug(base_slug: str, db: Session) -> str:
    slug = base_slug
    counter = 1
    while db.query(Analyst).filter(Analyst.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


@router.get("", response_model=List[AnalystOut])
def list_analysts(admin: bool = False, db: Session = Depends(get_db)):
    q = db.query(Analyst).filter(Analyst.is_active == True)
    if not admin:
        q = q.filter(Analyst.is_public == True)
    analysts = q.order_by(Analyst.name).all()
    result = []
    for analyst in analysts:
        score_data = compute_analyst_score(analyst.id, db)
        out = AnalystOut.model_validate(analyst)
        out.score = AnalystScore(**score_data)
        result.append(out)
    return result


@router.get("/{slug}", response_model=AnalystDetail)
def get_analyst(slug: str, db: Session = Depends(get_db)):
    analyst = (
        db.query(Analyst)
        .filter(Analyst.slug == slug)
        .options(
            selectinload(Analyst.predictions)
            .selectinload(Prediction.outcome),
            selectinload(Analyst.predictions)
            .selectinload(Prediction.statement),
        )
        .first()
    )
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    score_data = compute_analyst_score(analyst.id, db)
    out = AnalystDetail.model_validate(analyst)
    out.score = AnalystScore(**score_data)
    return out


@router.post("", response_model=AnalystOut, status_code=201)
def create_analyst(body: AnalystCreate, db: Session = Depends(get_db)):
    base_slug = _slugify(body.name)
    slug = _make_unique_slug(base_slug, db)

    try:
        profile_image_url = _fetch_photo_via_llm(body.name, _get_anthropic_client())
    except Exception:
        profile_image_url = None

    analyst = Analyst(
        name=body.name,
        slug=slug,
        bio=body.bio,
        substack_url=body.substack_url,
        youtube_channel_id=body.youtube_channel_id,
        website_url=body.website_url,
        podcast_rss_url=body.podcast_rss_url,
        twitter_handle=body.twitter_handle,
        profile_image_url=profile_image_url,
    )
    db.add(analyst)
    db.commit()
    db.refresh(analyst)

    score_data = compute_analyst_score(analyst.id, db)
    out = AnalystOut.model_validate(analyst)
    out.score = AnalystScore(**score_data)
    return out


@router.post("/{analyst_id}/collect", response_model=CollectResult)
def collect_data(analyst_id: int, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    # Run sequentially first — upgrades existing stubs before new collection starts
    retry_youtube_transcripts(analyst, db)

    # All collectors are independent I/O-bound tasks — run them in parallel.
    # Each thread gets its own DB session to avoid SQLAlchemy session conflicts.
    collectors = [
        collect_substack_posts,
        collect_news_mentions,
        collect_youtube_transcripts,
        collect_podcast_episodes,
        collect_youtube_guest_appearances,
        collect_podcast_guest_appearances,
        collect_tweets,
        collect_cnbc_transcripts,
        collect_website_posts,
        collect_media_mentions,
    ]

    def _run_collector(fn):
        thread_db = SessionLocal()
        try:
            thread_analyst = thread_db.query(Analyst).filter(Analyst.id == analyst_id).first()
            return fn(thread_analyst, thread_db)
        except Exception as exc:
            logger.error(f"{fn.__name__} failed: {exc}")
            return 0
        finally:
            thread_db.close()

    results: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=len(collectors)) as executor:
        futures = {executor.submit(_run_collector, fn): fn.__name__ for fn in collectors}
        for future in as_completed(futures):
            results[futures[future]] = future.result() or 0

    substack_new       = results.get("collect_substack_posts", 0)
    google_new         = results.get("collect_news_mentions", 0)
    youtube_new        = results.get("collect_youtube_transcripts", 0)
    podcast_new        = results.get("collect_podcast_episodes", 0)
    youtube_guest_new  = results.get("collect_youtube_guest_appearances", 0)
    podcast_guest_new  = results.get("collect_podcast_guest_appearances", 0)
    twitter_new        = results.get("collect_tweets", 0)
    cnbc_new           = results.get("collect_cnbc_transcripts", 0)
    website_new        = results.get("collect_website_posts", 0)
    media_new          = results.get("collect_media_mentions", 0)

    total_statements = db.query(Statement).filter(Statement.analyst_id == analyst_id).count()

    return CollectResult(
        analyst_id=analyst_id,
        substack_new=substack_new,
        google_news_new=google_new,
        youtube_new=youtube_new,
        podcast_new=podcast_new,
        youtube_guest_new=youtube_guest_new,
        podcast_guest_new=podcast_guest_new,
        twitter_new=twitter_new,
        cnbc_new=cnbc_new,
        total_new=substack_new + google_new + youtube_new + podcast_new + youtube_guest_new + podcast_guest_new + twitter_new + cnbc_new + website_new + media_new,
        total_statements=total_statements,
    )


@router.post("/{analyst_id}/process", response_model=ProcessResult)
def process_statements(analyst_id: int, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    client = _get_anthropic_client()

    unprocessed = (
        db.query(Statement)
        .filter(Statement.analyst_id == analyst_id, Statement.is_processed == False)
        .all()
    )

    statement_ids = [s.id for s in unprocessed]

    def _process_one(statement_id: int):
        """Returns (skipped: bool, predictions_count: int)."""
        thread_db = SessionLocal()
        try:
            statement = thread_db.query(Statement).filter(Statement.id == statement_id).first()
            if not statement:
                return False, 0
            preds = extract_predictions(statement, client, thread_db)
            statement.is_processed = True
            thread_db.commit()
            if preds is None:
                return True, 0   # skipped by pre-filter
            return False, len(preds)
        except Exception as exc:
            logger.error(f"Error processing statement {statement_id}: {exc}")
            thread_db.rollback()
            return False, 0
        finally:
            thread_db.close()

    statements_processed = 0
    statements_skipped = 0
    predictions_extracted = 0

    # max_workers=5 keeps concurrent Anthropic API calls within rate limits
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_process_one, sid): sid for sid in statement_ids}
        for future in as_completed(futures):
            skipped, count = future.result()
            if skipped:
                statements_skipped += 1
            else:
                statements_processed += 1
                predictions_extracted += count

    return ProcessResult(
        analyst_id=analyst_id,
        statements_processed=statements_processed,
        statements_skipped=statements_skipped,
        predictions_extracted=predictions_extracted,
    )


@router.post("/{analyst_id}/judge", response_model=JudgeResult)
def judge_predictions(analyst_id: int, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    client = _get_anthropic_client()

    # Find predictions without a judged outcome
    unjudged = (
        db.query(Prediction)
        .outerjoin(PredictionOutcome, Prediction.id == PredictionOutcome.prediction_id)
        .filter(
            Prediction.analyst_id == analyst_id,
            (PredictionOutcome.id == None) | (PredictionOutcome.llm_rating == None),
        )
        .all()
    )

    # Build calibration examples from past human-reviewed predictions for this analyst.
    # Prioritise corrections (human overrode the LLM) — they carry the strongest signal.
    # Cap at 8 examples to avoid unnecessary token bloat.
    reviewed = (
        db.query(Prediction, PredictionOutcome)
        .join(PredictionOutcome, Prediction.id == PredictionOutcome.prediction_id)
        .filter(
            Prediction.analyst_id == analyst_id,
            PredictionOutcome.is_finalized == True,
            PredictionOutcome.human_rating != None,
        )
        .all()
    )
    corrections = [
        {
            "prediction_text": p.prediction_text,
            "human_rating": o.human_rating.value,
            "llm_rating": o.llm_rating.value if o.llm_rating else None,
        }
        for p, o in reviewed
        if o.llm_rating != o.human_rating
    ]
    agreements = [
        {
            "prediction_text": p.prediction_text,
            "human_rating": o.human_rating.value,
            "llm_rating": o.llm_rating.value if o.llm_rating else None,
        }
        for p, o in reviewed
        if o.llm_rating == o.human_rating
    ]
    # Up to 5 corrections + 3 agreements = 8 examples max
    calibration_examples = corrections[:5] + agreements[:3]

    prediction_ids = [p.id for p in unjudged]

    def _judge_one(prediction_id: int) -> bool:
        """Run in a thread — each thread gets its own DB session."""
        thread_db = SessionLocal()
        try:
            prediction = thread_db.query(Prediction).filter(Prediction.id == prediction_id).first()
            if not prediction:
                return False
            outcome = judge_prediction(prediction, client, thread_db, calibration_examples)
            return outcome is not None
        except Exception as exc:
            logger.error(f"Error judging prediction {prediction_id}: {exc}")
            return False
        finally:
            thread_db.close()

    judged_count = 0
    # max_workers=5 keeps concurrent Anthropic API calls within rate limits
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_judge_one, pid): pid for pid in prediction_ids}
        for future in as_completed(futures):
            if future.result():
                judged_count += 1

    # Auto-generate narrative summary once enough judgments exist
    try:
        generate_analyst_summary(analyst, client, db)
    except Exception as exc:
        logger.warning(f"Summary generation failed for analyst {analyst_id}: {exc}")

    return JudgeResult(analyst_id=analyst_id, predictions_judged=judged_count)


@router.post("/lookup", tags=["analysts"])
def lookup_analyst(body: dict, db: Session = Depends(get_db)):
    """Use Claude to find known online sources for a named analyst."""
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    client = _get_anthropic_client()

    prompt = f"""I need to find the online presence of a public analyst, commentator, or author named "{name}".

Please provide their known online profiles in this exact JSON format:
{{
  "bio": "1-2 sentence description of who they are and their area of expertise",
  "substack_url": "their Substack URL if they have one, e.g. https://name.substack.com, or null",
  "youtube_channel_url": "their YouTube channel URL if they have one, or null",
  "website_url": "their primary personal or professional website, or null",
  "podcast_rss_url": "RSS feed URL for their podcast if they have one, or null"
}}

Only include URLs you are confident are correct for this specific person. If you are not sure about a URL, return null for that field. Respond with valid JSON only."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM lookup failed: {exc}")

    raw = response.content[0].text.strip()
    # Extract JSON object robustly — handles ```json fences and surrounding text
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        raise HTTPException(status_code=500, detail="Could not parse LLM response")
    try:
        data = json.loads(json_match.group())
    except Exception:
        raise HTTPException(status_code=500, detail="Could not parse LLM response")

    profile_image_url = _fetch_photo_via_llm(name, client)

    return {
        "bio": data.get("bio") or None,
        "substack_url": data.get("substack_url") or None,
        "youtube_channel_id": data.get("youtube_channel_url") or None,
        "website_url": data.get("website_url") or None,
        "podcast_rss_url": data.get("podcast_rss_url") or None,
        "profile_image_url": profile_image_url,
    }


@router.patch("/{analyst_id}", response_model=AnalystOut)
def update_analyst(analyst_id: int, body: AnalystUpdate, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(analyst, field, value)
    db.commit()
    db.refresh(analyst)
    score_data = compute_analyst_score(analyst.id, db)
    out = AnalystOut.model_validate(analyst)
    out.score = AnalystScore(**score_data)
    return out


@router.post("/{analyst_id}/fetch-photo", response_model=AnalystOut)
def fetch_photo(analyst_id: int, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")
    image_url = _fetch_photo_via_llm(analyst.name, _get_anthropic_client())
    if not image_url:
        raise HTTPException(status_code=404, detail="No photo found for this analyst")
    analyst.profile_image_url = image_url
    db.commit()
    db.refresh(analyst)
    score_data = compute_analyst_score(analyst.id, db)
    out = AnalystOut.model_validate(analyst)
    out.score = AnalystScore(**score_data)
    return out


@router.post("/{analyst_id}/summarize")
def regenerate_summary(analyst_id: int, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")
    client = _get_anthropic_client()
    summary = generate_analyst_summary(analyst, client, db)
    if summary is None:
        raise HTTPException(status_code=400, detail="Not enough rated predictions to summarize (need 5+ non-unresolved judgments)")
    return {"summary": summary}


@router.get("/{analyst_id}/score", response_model=AnalystScore)
def get_score(analyst_id: int, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    score_data = compute_analyst_score(analyst_id, db)
    return AnalystScore(**score_data)
