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
    # unresolved / not_a_prediction excluded from score calculation
}


def _lead_time_weight(lead_days: Optional[int]) -> float:
    """
    Return a weight multiplier based on how far in advance the prediction was made.
    Predictions made further out are harder and worth more credit.
    """
    if lead_days is None or lead_days < 0:
        return 1.0  # unknown lead time → neutral weight
    if lead_days <= 7:
        return 0.5   # called it the same week — minimal credit
    if lead_days <= 30:
        return 0.75  # within a month
    if lead_days <= 90:
        return 1.0   # 1–3 months — baseline
    if lead_days <= 365:
        return 1.5   # within the year
    if lead_days <= 365 * 3:
        return 2.0   # 1–3 years out
    if lead_days <= 365 * 5:
        return 2.5   # 3–5 years out
    return 3.0       # 5+ years — long-range forecast


def _letter_grade(score: Optional[float]) -> Optional[str]:
    """Convert a 0-100 accuracy score to a letter grade."""
    if score is None:
        return None
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 75: return "A-"
    if score >= 70: return "B+"
    if score >= 65: return "B"
    if score >= 60: return "B-"
    if score >= 55: return "C+"
    if score >= 50: return "C"
    if score >= 45: return "C-"
    if score >= 35: return "D"
    return "F"


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

    # Compute accuracy scores (exclude unresolved and not_a_prediction)
    scoreable_outcomes = [
        o for o in finalized_outcomes
        if o.human_rating and o.human_rating not in (RatingValue.unresolved, RatingValue.not_a_prediction)
    ]

    if scoreable_outcomes:
        # Unweighted accuracy
        raw_scores = [RATING_SCORES.get(o.human_rating, 0.0) for o in scoreable_outcomes]
        accuracy_score = round((sum(raw_scores) / len(raw_scores)) * 100, 1)

        # Lead-time weighted accuracy
        weighted_sum = 0.0
        weight_total = 0.0
        for outcome in scoreable_outcomes:
            pred = db.query(Prediction).filter(Prediction.id == outcome.prediction_id).first()
            lead_days = None
            if pred and pred.target_date and pred.statement and pred.statement.published_at:
                lead_days = (pred.target_date - pred.statement.published_at).days
            w = _lead_time_weight(lead_days)
            weighted_sum += RATING_SCORES.get(outcome.human_rating, 0.0) * w
            weight_total += w
        weighted_accuracy_score = round((weighted_sum / weight_total) * 100, 1) if weight_total > 0 else accuracy_score
    else:
        accuracy_score = None
        weighted_accuracy_score = None

    display_score = weighted_accuracy_score if weighted_accuracy_score is not None else accuracy_score

    return {
        "total_predictions": total_predictions,
        "judged_predictions": judged_predictions,
        "finalized_predictions": finalized_predictions,
        "accuracy_score": accuracy_score,
        "weighted_accuracy_score": weighted_accuracy_score,
        "letter_grade": _letter_grade(display_score),
        "rating_breakdown": rating_breakdown,
    }
