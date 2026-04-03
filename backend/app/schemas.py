from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel
from app.models import SourceType, RatingValue


# ── Analyst ──────────────────────────────────────────────────────────────────

class AnalystCreate(BaseModel):
    name: str
    bio: Optional[str] = None
    substack_url: Optional[str] = None
    youtube_channel_id: Optional[str] = None
    website_url: Optional[str] = None
    podcast_rss_url: Optional[str] = None


class AnalystScore(BaseModel):
    total_predictions: int
    judged_predictions: int
    finalized_predictions: int
    accuracy_score: Optional[float]  # 0-100
    rating_breakdown: dict[str, int]

    model_config = {"from_attributes": True}


class AnalystOut(BaseModel):
    id: int
    name: str
    slug: str
    bio: Optional[str]
    substack_url: Optional[str]
    youtube_channel_id: Optional[str]
    website_url: Optional[str]
    podcast_rss_url: Optional[str]
    twitter_handle: Optional[str]
    profile_image_url: Optional[str]
    narrative_summary: Optional[str]
    summary_updated_at: Optional[datetime]
    is_active: bool
    created_at: datetime
    score: Optional[AnalystScore] = None

    model_config = {"from_attributes": True}


# ── Statement ─────────────────────────────────────────────────────────────────

class StatementOut(BaseModel):
    id: int
    analyst_id: int
    source_type: SourceType
    source_url: str
    source_title: Optional[str]
    content: str
    published_at: Optional[datetime]
    collected_at: datetime
    is_processed: bool

    model_config = {"from_attributes": True}


# ── PredictionOutcome ─────────────────────────────────────────────────────────

class OutcomeOut(BaseModel):
    id: int
    prediction_id: int
    evidence_text: Optional[str]
    evidence_urls: Optional[str]
    llm_rating: Optional[RatingValue]
    llm_reasoning: Optional[str]
    human_rating: Optional[RatingValue]
    human_notes: Optional[str]
    is_finalized: bool
    judged_at: Optional[datetime]
    reviewed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class OutcomeUpdate(BaseModel):
    human_rating: RatingValue
    human_notes: Optional[str] = None


# ── Prediction ────────────────────────────────────────────────────────────────

class StatementMeta(BaseModel):
    """Lightweight statement — source metadata only, no content. Used in prediction lists."""
    id: int
    source_type: SourceType
    source_url: str
    source_title: Optional[str]
    published_at: Optional[datetime]

    model_config = {"from_attributes": True}


class PredictionOut(BaseModel):
    id: int
    statement_id: int
    analyst_id: int
    prediction_text: str
    predicted_event: Optional[str]
    predicted_timeframe: Optional[str]
    confidence_language: Optional[str]
    extracted_at: datetime
    outcome: Optional[OutcomeOut] = None
    statement: Optional[StatementMeta] = None  # metadata only, no content

    model_config = {"from_attributes": True}


# ── Analyst Detail (with predictions) ────────────────────────────────────────

class AnalystDetail(AnalystOut):
    predictions: List[PredictionOut] = []

    model_config = {"from_attributes": True}


# ── Review Queue Item ─────────────────────────────────────────────────────────

class ReviewQueueItem(BaseModel):
    outcome_id: int
    prediction_id: int
    prediction_text: str
    predicted_event: Optional[str]
    predicted_timeframe: Optional[str]
    confidence_language: Optional[str]
    statement_title: Optional[str]
    statement_url: str
    statement_source_type: SourceType
    published_at: Optional[datetime]
    analyst_name: str
    analyst_slug: str
    llm_rating: Optional[RatingValue]
    llm_reasoning: Optional[str]
    evidence_text: Optional[str]
    evidence_urls: Optional[str]
    judged_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Collection / Processing Results ──────────────────────────────────────────

class CollectResult(BaseModel):
    analyst_id: int
    substack_new: int
    google_news_new: int
    youtube_new: int
    podcast_new: int
    youtube_guest_new: int
    podcast_guest_new: int
    twitter_new: int
    cnbc_new: int
    total_new: int
    total_statements: int


class ProcessResult(BaseModel):
    analyst_id: int
    statements_processed: int
    statements_skipped: int  # skipped by pre-filter (no prediction signals)
    predictions_extracted: int


class JudgeResult(BaseModel):
    analyst_id: int
    predictions_judged: int
