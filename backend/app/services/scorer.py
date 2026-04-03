import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Analyst, Prediction, PredictionOutcome, RatingValue

logger = logging.getLogger(__name__)

# Score mapping for finalized human ratings
RATING_SCORES = {
    RatingValue.true: 1.0,
    RatingValue.somewhat_true: 0.67,
    RatingValue.mostly_untrue: 0.33,
    RatingValue.untrue: 0.0,
    # unresolved is excluded from score calculation
}


def compute_analyst_score(analyst_id: int, db: Session) -> dict:
    """
    Compute the accuracy score for an analyst.

    Only finalized outcomes (is_finalized=True, human_rating is not null) count.
    Unresolved ratings are excluded from the accuracy calculation.

    Returns a dict with:
        total_predictions, judged_predictions, finalized_predictions,
        accuracy_score (0-100 float or None), rating_breakdown
    """
    analyst = db.query(Analyst).filter(Analyst.id == analyst_id).first()
    if not analyst:
        return {
            "total_predictions": 0,
            "judged_predictions": 0,
            "finalized_predictions": 0,
            "accuracy_score": None,
            "rating_breakdown": {},
        }

    # Total predictions for the analyst
    total_predictions = (
        db.query(Prediction)
        .filter(Prediction.analyst_id == analyst_id)
        .count()
    )

    # Predictions with any LLM judgment
    judged_predictions = (
        db.query(Prediction)
        .join(PredictionOutcome, Prediction.id == PredictionOutcome.prediction_id)
        .filter(
            Prediction.analyst_id == analyst_id,
            PredictionOutcome.llm_rating.isnot(None),
        )
        .count()
    )

    # Finalized outcomes (human reviewed)
    finalized_outcomes = (
        db.query(PredictionOutcome)
        .join(Prediction, PredictionOutcome.prediction_id == Prediction.id)
        .filter(
            Prediction.analyst_id == analyst_id,
            PredictionOutcome.is_finalized == True,
            PredictionOutcome.human_rating.isnot(None),
        )
        .all()
    )

    finalized_predictions = len(finalized_outcomes)

    # Build rating breakdown
    rating_breakdown: dict[str, int] = {r.value: 0 for r in RatingValue}
    for outcome in finalized_outcomes:
        if outcome.human_rating:
            rating_breakdown[outcome.human_rating.value] = (
                rating_breakdown.get(outcome.human_rating.value, 0) + 1
            )

    # Compute accuracy score (exclude unresolved)
    scoreable_outcomes = [
        o for o in finalized_outcomes
        if o.human_rating and o.human_rating != RatingValue.unresolved
    ]

    if scoreable_outcomes:
        total_score = sum(RATING_SCORES.get(o.human_rating, 0.0) for o in scoreable_outcomes)
        accuracy_score = round((total_score / len(scoreable_outcomes)) * 100, 1)
    else:
        accuracy_score = None

    return {
        "total_predictions": total_predictions,
        "judged_predictions": judged_predictions,
        "finalized_predictions": finalized_predictions,
        "accuracy_score": accuracy_score,
        "rating_breakdown": rating_breakdown,
    }
