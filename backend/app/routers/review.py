from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Analyst, Prediction, PredictionOutcome, Statement
from app.schemas import OutcomeOut, OutcomeUpdate, ReviewQueueItem

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue", response_model=List[ReviewQueueItem])
def get_review_queue(db: Session = Depends(get_db)):
    """Return all unfinalized prediction outcomes with full context."""
    outcomes = (
        db.query(PredictionOutcome)
        .filter(PredictionOutcome.is_finalized == False)
        .order_by(PredictionOutcome.judged_at.desc().nullslast())
        .all()
    )

    items = []
    for outcome in outcomes:
        prediction = db.query(Prediction).filter(Prediction.id == outcome.prediction_id).first()
        if not prediction:
            continue
        statement = db.query(Statement).filter(Statement.id == prediction.statement_id).first()
        if not statement:
            continue
        analyst = db.query(Analyst).filter(Analyst.id == prediction.analyst_id).first()
        if not analyst:
            continue

        items.append(
            ReviewQueueItem(
                outcome_id=outcome.id,
                prediction_id=prediction.id,
                prediction_text=prediction.prediction_text,
                predicted_event=prediction.predicted_event,
                predicted_timeframe=prediction.predicted_timeframe,
                confidence_language=prediction.confidence_language,
                statement_title=statement.source_title,
                statement_url=statement.source_url,
                statement_source_type=statement.source_type,
                published_at=statement.published_at,
                analyst_name=analyst.name,
                analyst_slug=analyst.slug,
                llm_rating=outcome.llm_rating,
                llm_reasoning=outcome.llm_reasoning,
                evidence_text=outcome.evidence_text,
                evidence_urls=outcome.evidence_urls,
                judged_at=outcome.judged_at,
            )
        )

    return items


@router.patch("/{outcome_id}", response_model=OutcomeOut)
def update_outcome(
    outcome_id: int,
    body: OutcomeUpdate,
    db: Session = Depends(get_db),
):
    """Apply human rating to an outcome and mark it finalized."""
    outcome = db.query(PredictionOutcome).filter(PredictionOutcome.id == outcome_id).first()
    if not outcome:
        raise HTTPException(status_code=404, detail="Outcome not found")

    outcome.human_rating = body.human_rating
    outcome.human_notes = body.human_notes
    outcome.is_finalized = True
    outcome.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(outcome)
    return outcome
