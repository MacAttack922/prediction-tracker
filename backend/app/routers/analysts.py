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


def _fetch_wikipedia_image(name: str) -> Optional[str]:
    """Try to get a profile photo URL from Wikipedia for a named person."""
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(name)}"
    try:
        with httpx.Client(follow_redirects=True, timeout=8) as client:
            r = client.get(url, headers={"User-Agent": "prediction-tracker/1.0"})
        if r.status_code == 200:
            data = r.json()
            return (data.get("thumbnail") or data.get("originalimage") or {}).get("source")
    except Exception as exc:
        logger.debug(f"Wikipedia image fetch failed for {name!r}: {exc}")
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
def list_analysts(db: Session = Depends(get_db)):
    analysts = db.query(Analyst).filter(Analyst.is_active == True).order_by(Analyst.name).all()
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

    analyst = Analyst(
        name=body.name,
        slug=slug,
        bio=body.bio,
        substack_url=body.substack_url,
        youtube_channel_id=body.youtube_channel_id,
        website_url=body.website_url,
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

    retry_youtube_transcripts(analyst, db)  # upgrade description stubs if transcripts now available
    substack_new = collect_substack_posts(analyst, db)
    google_new = collect_news_mentions(analyst, db)
    youtube_new = collect_youtube_transcripts(analyst, db)
    podcast_new = collect_podcast_episodes(analyst, db)
    youtube_guest_new = collect_youtube_guest_appearances(analyst, db)
    podcast_guest_new = collect_podcast_guest_appearances(analyst, db)
    twitter_new = collect_tweets(analyst, db)
    cnbc_new = collect_cnbc_transcripts(analyst, db)
    website_new = collect_website_posts(analyst, db)
    media_new = collect_media_mentions(analyst, db)

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

    statements_processed = 0
    predictions_extracted = 0

    for statement in unprocessed:
        try:
            preds = extract_predictions(statement, client, db)
            predictions_extracted += len(preds)
            statement.is_processed = True
            db.commit()
            statements_processed += 1
        except Exception as exc:
            logger.error(f"Error processing statement {statement.id}: {exc}")
            db.rollback()

    return ProcessResult(
        analyst_id=analyst_id,
        statements_processed=statements_processed,
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

    profile_image_url = _fetch_wikipedia_image(name)

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
    image_url = _fetch_wikipedia_image(analyst.name)
    if not image_url:
        raise HTTPException(status_code=404, detail="No Wikipedia photo found for this analyst")
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
