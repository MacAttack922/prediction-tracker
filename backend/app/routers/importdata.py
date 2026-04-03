"""
Temporary one-shot data import endpoint.
Protected by IMPORT_SECRET env var.
Remove this file and its router registration after the import is done.
"""
import os
import json
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Analyst, Statement, Prediction, PredictionOutcome, SourceType, RatingValue

router = APIRouter(prefix="/api/import", tags=["import"])


def _require_secret(x_import_secret: Optional[str] = Header(None)):
    secret = os.getenv("IMPORT_SECRET", "")
    if not secret or x_import_secret != secret:
        raise HTTPException(status_code=403, detail="Forbidden")


class OutcomeData(BaseModel):
    id: int
    prediction_id: int
    evidence_text: Optional[str]
    evidence_urls: Optional[str]
    llm_rating: Optional[str]
    llm_reasoning: Optional[str]
    human_rating: Optional[str]
    human_notes: Optional[str]
    is_finalized: bool
    judged_at: Optional[str]
    reviewed_at: Optional[str]


class PredictionData(BaseModel):
    id: int
    statement_id: int
    analyst_id: int
    prediction_text: str
    predicted_event: Optional[str]
    predicted_timeframe: Optional[str]
    confidence_language: Optional[str]
    extracted_at: str
    outcome: Optional[OutcomeData]


class StatementData(BaseModel):
    id: int
    analyst_id: int
    source_type: str
    source_url: str
    source_title: Optional[str]
    content: str
    published_at: Optional[str]
    collected_at: str
    is_processed: bool


class AnalystData(BaseModel):
    id: int
    name: str
    slug: str
    bio: Optional[str]
    substack_url: Optional[str]
    youtube_channel_id: Optional[str]
    website_url: Optional[str]
    podcast_rss_url: Optional[str]
    profile_image_url: Optional[str]
    narrative_summary: Optional[str]
    summary_updated_at: Optional[str]
    is_active: bool
    created_at: str
    statements: List[StatementData] = []
    predictions: List[PredictionData] = []


class ImportPayload(BaseModel):
    analysts: List[AnalystData]


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


@router.post("")
def import_data(payload: ImportPayload, db: Session = Depends(get_db), _=Depends(_require_secret)):
    counts = {"analysts": 0, "statements": 0, "predictions": 0, "outcomes": 0}

    for a in payload.analysts:
        existing = db.query(Analyst).filter(Analyst.id == a.id).first()
        if not existing:
            analyst = Analyst(
                id=a.id, name=a.name, slug=a.slug, bio=a.bio,
                substack_url=a.substack_url, youtube_channel_id=a.youtube_channel_id,
                website_url=a.website_url, podcast_rss_url=a.podcast_rss_url,
                profile_image_url=a.profile_image_url, narrative_summary=a.narrative_summary,
                summary_updated_at=_parse_dt(a.summary_updated_at),
                is_active=a.is_active, created_at=_parse_dt(a.created_at) or datetime.utcnow(),
            )
            db.add(analyst)
            db.flush()
            counts["analysts"] += 1

        for s in a.statements:
            if db.query(Statement).filter(Statement.id == s.id).first():
                continue
            stmt = Statement(
                id=s.id, analyst_id=s.analyst_id,
                source_type=SourceType(s.source_type),
                source_url=s.source_url, source_title=s.source_title,
                content=s.content, published_at=_parse_dt(s.published_at),
                collected_at=_parse_dt(s.collected_at) or datetime.utcnow(),
                is_processed=s.is_processed,
            )
            db.add(stmt)
            db.flush()
            counts["statements"] += 1

        for p in a.predictions:
            if db.query(Prediction).filter(Prediction.id == p.id).first():
                continue
            pred = Prediction(
                id=p.id, statement_id=p.statement_id, analyst_id=p.analyst_id,
                prediction_text=p.prediction_text, predicted_event=p.predicted_event,
                predicted_timeframe=p.predicted_timeframe,
                confidence_language=p.confidence_language,
                extracted_at=_parse_dt(p.extracted_at) or datetime.utcnow(),
            )
            db.add(pred)
            db.flush()
            counts["predictions"] += 1

            if p.outcome:
                o = p.outcome
                if not db.query(PredictionOutcome).filter(PredictionOutcome.id == o.id).first():
                    outcome = PredictionOutcome(
                        id=o.id, prediction_id=o.prediction_id,
                        evidence_text=o.evidence_text, evidence_urls=o.evidence_urls,
                        llm_rating=RatingValue(o.llm_rating) if o.llm_rating else None,
                        llm_reasoning=o.llm_reasoning,
                        human_rating=RatingValue(o.human_rating) if o.human_rating else None,
                        human_notes=o.human_notes, is_finalized=o.is_finalized,
                        judged_at=_parse_dt(o.judged_at), reviewed_at=_parse_dt(o.reviewed_at),
                    )
                    db.add(outcome)
                    db.flush()
                    counts["outcomes"] += 1

    db.commit()
    return {"status": "ok", "imported": counts}
