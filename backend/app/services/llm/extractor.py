import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, List, Dict, Any

from sqlalchemy.orm import Session

from app.models import Prediction

if TYPE_CHECKING:
    import anthropic
    from app.models import Statement

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are an expert analyst specializing in identifying predictions and forecasts in text.

Today's date is April 2, 2026.

Your task is to extract all predictions from the provided text — that is, claims about future events, outcomes, or states of the world that the author asserts will happen or is likely to happen.

Focus on:
- Explicit forecasts ("X will happen", "I expect Y")
- Implicit predictions ("when X happens", "once Y occurs")
- Conditional predictions ("if X then Y")

Do NOT include:
- Historical descriptions of past events
- General opinions without a predictive element
- Rhetorical questions

For each prediction, extract:
- prediction_text: The exact quote or very close paraphrase from the text
- predicted_event: A brief (1 sentence) description of what is being predicted
- predicted_timeframe: The timeframe mentioned (e.g., "by end of 2024", "within 6 months", "next year"), or null if none
- confidence_language: Any hedging or confidence words used (e.g., "I think", "certainly", "likely", "might", "I believe"), or null if none

Respond ONLY with a valid JSON array. If there are no predictions, respond with an empty array [].

Example response:
[
  {
    "prediction_text": "I think inflation will fall below 3% by mid-2024",
    "predicted_event": "Inflation falling below 3%",
    "predicted_timeframe": "by mid-2024",
    "confidence_language": "I think"
  }
]"""

NEWS_EXTRACTION_SYSTEM_PROMPT = """You are an expert analyst specializing in identifying predictions and forecasts made by specific individuals.

Today's date is April 2, 2026.

You will be given a news article and the name of an analyst. Your task is to extract predictions that are directly attributed to that analyst — things they said, wrote, or were quoted as saying. Ignore predictions or claims made by journalists, other sources, or anyone other than the named analyst.

Focus on:
- Direct quotes from the analyst containing forecasts
- Paraphrased statements attributed to the analyst with predictive content
- Explicit forecasts ("X will happen", "I expect Y")
- Conditional predictions ("if X then Y")

Do NOT include:
- Statements made by journalists or other people
- Historical descriptions of past events
- General opinions without a predictive element

For each prediction, extract:
- prediction_text: The exact quote or close paraphrase attributed to the analyst
- predicted_event: A brief (1 sentence) description of what is being predicted
- predicted_timeframe: The timeframe mentioned, or null if none
- confidence_language: Hedging or confidence words used, or null if none

Respond ONLY with a valid JSON array. If there are no predictions attributed to the analyst, respond with an empty array []."""


def extract_predictions(statement: "Statement", anthropic_client: "anthropic.Anthropic", db: Session) -> List[Prediction]:
    """Extract predictions from a statement using Claude and save them to the database."""
    if not statement.content or len(statement.content.strip()) < 50:
        logger.info(f"Statement {statement.id} too short, skipping extraction.")
        return []

    # Truncate very long content to avoid token limits
    content = statement.content[:8000] if len(statement.content) > 8000 else statement.content

    # For third-party content (news, guest videos, guest podcasts), use the quote-aware
    # prompt so we only extract predictions attributed to the named analyst, not the host.
    THIRD_PARTY_SOURCES = {"google_news", "youtube_guest", "podcast_guest"}
    is_news = statement.source_type.value in THIRD_PARTY_SOURCES
    if is_news:
        analyst_name = statement.analyst.name if statement.analyst else "the analyst"
        system_prompt = NEWS_EXTRACTION_SYSTEM_PROMPT
        user_message = f"""Analyst name: {analyst_name}

News article:
---
{content}
---

Extract only predictions directly attributed to {analyst_name}. Respond ONLY with a valid JSON array."""
    else:
        system_prompt = EXTRACTION_SYSTEM_PROMPT
        user_message = f"""Please extract all predictions from the following text:

---
{content}
---

Remember to respond ONLY with a valid JSON array."""

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        logger.error(f"LLM call failed for statement {statement.id}: {exc}")
        return []

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1]) if len(lines) > 2 else raw_text

    try:
        predictions_data: List[Dict[str, Any]] = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse LLM response as JSON for statement {statement.id}: {exc}\nRaw: {raw_text[:500]}")
        return []

    if not isinstance(predictions_data, list):
        logger.warning(f"LLM returned non-list for statement {statement.id}")
        return []

    created_predictions: List[Prediction] = []
    for item in predictions_data:
        if not isinstance(item, dict):
            continue
        prediction_text = item.get("prediction_text", "").strip()
        if not prediction_text:
            continue

        prediction = Prediction(
            statement_id=statement.id,
            analyst_id=statement.analyst_id,
            prediction_text=prediction_text,
            predicted_event=item.get("predicted_event") or None,
            predicted_timeframe=item.get("predicted_timeframe") or None,
            confidence_language=item.get("confidence_language") or None,
            extracted_at=datetime.utcnow(),
        )
        db.add(prediction)
        try:
            db.flush()
            created_predictions.append(prediction)
        except Exception as exc:
            db.rollback()
            logger.error(f"Error saving prediction: {exc}")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Error committing predictions for statement {statement.id}: {exc}")
        return []

    logger.info(f"Extracted {len(created_predictions)} predictions from statement {statement.id}.")
    return created_predictions
