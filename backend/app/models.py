import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class SourceType(str, enum.Enum):
    substack = "substack"
    google_news = "google_news"
    youtube = "youtube"
    website = "website"
    podcast = "podcast"
    youtube_guest = "youtube_guest"
    podcast_guest = "podcast_guest"
    twitter = "twitter"
    cnbc = "cnbc"


class RatingValue(str, enum.Enum):
    untrue = "untrue"
    mostly_untrue = "mostly_untrue"
    somewhat_true = "somewhat_true"
    true = "true"
    unresolved = "unresolved"
    not_a_prediction = "not_a_prediction"


class Analyst(Base):
    __tablename__ = "analysts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    bio = Column(Text, nullable=True)
    substack_url = Column(String(500), nullable=True)
    youtube_channel_id = Column(String(255), nullable=True)
    website_url = Column(String(500), nullable=True)
    podcast_rss_url = Column(String(500), nullable=True)
    twitter_handle = Column(String(100), nullable=True)
    profile_image_url = Column(String(1000), nullable=True)
    narrative_summary = Column(Text, nullable=True)
    summary_updated_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    statements = relationship("Statement", back_populates="analyst", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="analyst", cascade="all, delete-orphan")


class Statement(Base):
    __tablename__ = "statements"

    id = Column(Integer, primary_key=True, index=True)
    analyst_id = Column(Integer, ForeignKey("analysts.id"), nullable=False)
    source_type = Column(SAEnum(SourceType), nullable=False)
    source_url = Column(String(1000), nullable=False)
    source_title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    published_at = Column(DateTime, nullable=True)
    collected_at = Column(DateTime, default=datetime.utcnow)
    is_processed = Column(Boolean, default=False)

    analyst = relationship("Analyst", back_populates="statements")
    predictions = relationship("Prediction", back_populates="statement", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("analyst_id", "source_url", name="uq_analyst_source_url"),
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    statement_id = Column(Integer, ForeignKey("statements.id"), nullable=False)
    analyst_id = Column(Integer, ForeignKey("analysts.id"), nullable=False)
    prediction_text = Column(Text, nullable=False)
    predicted_event = Column(Text, nullable=True)
    predicted_timeframe = Column(String(255), nullable=True)
    confidence_language = Column(String(500), nullable=True)
    extracted_at = Column(DateTime, default=datetime.utcnow)

    statement = relationship("Statement", back_populates="predictions")
    analyst = relationship("Analyst", back_populates="predictions")
    outcome = relationship("PredictionOutcome", back_populates="prediction", uselist=False, cascade="all, delete-orphan")


class PredictionOutcome(Base):
    __tablename__ = "prediction_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    prediction_id = Column(Integer, ForeignKey("predictions.id"), unique=True, nullable=False)
    evidence_text = Column(Text, nullable=True)
    evidence_urls = Column(Text, nullable=True)  # JSON string
    llm_rating = Column(SAEnum(RatingValue), nullable=True)
    llm_reasoning = Column(Text, nullable=True)
    human_rating = Column(SAEnum(RatingValue), nullable=True)
    human_notes = Column(Text, nullable=True)
    is_finalized = Column(Boolean, default=False)
    judged_at = Column(DateTime, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    prediction = relationship("Prediction", back_populates="outcome")
