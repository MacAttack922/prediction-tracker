import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.models import Prediction, PredictionOutcome, RatingValue

if TYPE_CHECKING:
    import anthropic
    from app.models import Analyst

logger = logging.getLogger(__name__)

SUMMARY_THRESHOLD = 5  # minimum finalized judgments before generating a summary

RATING_LABELS = {
    RatingValue.true: "true",
    RatingValue.somewhat_true: "somewhat true",
    RatingValue.mostly_untrue: "mostly untrue",
    RatingValue.untrue: "untrue",
    RatingValue.unresolved: "unresolved",
}


def generate_analyst_summary(
    analyst: "Analyst",
    anthropic_client: "anthropic.Anthropic",
    db: Session,
) -> Optional[str]:
    """Generate a narrative accuracy summary for an analyst if they have enough judgments."""

    finalized = (
        db.query(PredictionOutcome)
        .join(Prediction, PredictionOutcome.prediction_id == Prediction.id)
        .filter(
            Prediction.analyst_id == analyst.id,
            PredictionOutcome.is_finalized == True,
            PredictionOutcome.human_rating != None,
            PredictionOutcome.human_rating != RatingValue.unresolved,
        )
        .all()
    )

    if len(finalized) < SUMMARY_THRESHOLD:
        logger.info(
            f"{analyst.name} has {len(finalized)} finalized judgments "
            f"(need {SUMMARY_THRESHOLD}), skipping summary."
        )
        return None

    # Build a concise list of rated predictions for the prompt
    prediction_lines = []
    for outcome in finalized:
        pred = outcome.prediction
        rating = RATING_LABELS.get(outcome.human_rating, str(outcome.human_rating))
        prediction_lines.append(f'- [{rating.upper()}] "{pred.prediction_text}"')

    predictions_text = "\n".join(prediction_lines)

    prompt = f"""You are writing a brief analytical summary for a public prediction-tracking website.

Analyst: {analyst.name}
{f'Bio: {analyst.bio}' if analyst.bio else ''}

Rated predictions ({len(finalized)} total):
{predictions_text}

Write a 4-sentence narrative summary that:
1. Opens with an overall accuracy assessment (e.g. strong track record, mixed record, poor track record)
2. Describes what topics or domains their predictions focus on
3. Notes any patterns — areas where they tend to be right or wrong, overconfidence, appropriate hedging, etc.
4. Closes with a one-sentence characterisation of their predictive style

Write in third person. Be specific and analytical, not generic. Do not mention the website or the rating system. Output only the summary paragraph, no headings or bullet points."""

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = response.content[0].text.strip()
    except Exception as exc:
        logger.error(f"Failed to generate summary for {analyst.name}: {exc}")
        return None

    analyst.narrative_summary = summary
    analyst.summary_updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"Generated summary for {analyst.name}.")
    return summary
