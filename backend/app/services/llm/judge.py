import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List

from urllib.parse import quote_plus

import feedparser

from app.models import PredictionOutcome, RatingValue

if TYPE_CHECKING:
    import anthropic
    from app.models import Prediction

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are an impartial fact-checker tasked with evaluating the accuracy of predictions.

Given a prediction and evidence gathered from news sources, rate the prediction's accuracy using one of these ratings:
- true: The predicted event happened largely as described
- somewhat_true: The event partially happened, or happened with significant caveats
- mostly_untrue: The event mostly did not happen, or happened in a very different way than predicted
- untrue: The predicted event clearly did not happen
- unresolved: The event hasn't happened yet, is still in progress, or there is insufficient evidence to judge

CRITICAL RULES — follow these strictly:
1. DEFAULT TO "unresolved". Only use true/somewhat_true/mostly_untrue/untrue if you have clear, specific evidence from the provided news sources that the event definitively happened or did not happen.
2. If the news evidence is absent, vague, or does not directly confirm or deny the predicted event, rate as "unresolved".
3. If the prediction concerns events that could plausibly still lie in the future as of today's date (provided in the user message), rate as "unresolved".
4. Do NOT use your general world knowledge or reasoning to infer an outcome — only rate based on what the provided evidence explicitly confirms.
5. When in doubt, choose "unresolved".

Your response must be valid JSON with exactly these fields:
{
  "rating": "<one of the five values above>",
  "reasoning": "<2-4 sentences explaining your rating, citing specific evidence>",
  "evidence_summary": "<1-2 sentence summary of the most relevant evidence you found>"
}"""


def _search_google_news_for_evidence(query: str, max_results: int = 10) -> list[dict]:
    """Search Google News RSS for evidence related to a predicted event."""
    encoded_query = quote_plus(query)
    feed_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(feed_url)
        results = []
        for entry in feed.entries[:max_results]:
            results.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "published": entry.get("published", ""),
            })
        return results
    except Exception as exc:
        logger.warning(f"Google News search failed for '{query}': {exc}")
        return []


def _build_examples_block(examples: List[dict]) -> str:
    """Format past human-rated predictions as few-shot examples for the LLM."""
    if not examples:
        return ""
    lines = ["---", "CALIBRATION EXAMPLES — past predictions rated by the human reviewer:"]
    for ex in examples:
        correction = ""
        if ex.get("llm_rating") and ex["llm_rating"] != ex["human_rating"]:
            correction = f" (AI initially said: {ex['llm_rating']} — human corrected to: {ex['human_rating']})"
        else:
            correction = f" (rating: {ex['human_rating']})"
        lines.append(
            f"\nPrediction: \"{ex['prediction_text'][:200]}\"\n"
            f"Final verdict{correction}"
        )
    lines.append("---")
    lines.append("Use the above examples to calibrate your rating to match the human reviewer's standard.")
    return "\n".join(lines)


def judge_prediction(
    prediction: "Prediction",
    anthropic_client: "anthropic.Anthropic",
    db: Session,
    calibration_examples: Optional[List[dict]] = None,
) -> Optional[PredictionOutcome]:
    """Judge a prediction's accuracy using news evidence and Claude."""
    # Check if outcome already exists
    existing = (
        db.query(PredictionOutcome)
        .filter(PredictionOutcome.prediction_id == prediction.id)
        .first()
    )
    if existing and existing.llm_rating is not None:
        logger.info(f"Prediction {prediction.id} already judged, skipping.")
        return existing

    # Step 1: Gather evidence from Google News
    search_query = prediction.predicted_event or prediction.prediction_text[:150]
    evidence_items = _search_google_news_for_evidence(search_query)

    # Build evidence text
    evidence_parts = []
    evidence_urls = []
    for item in evidence_items:
        if item.get("title"):
            evidence_parts.append(
                f"- [{item['title']}]({item.get('url', '')})\n  {item.get('summary', '')}"
            )
            if item.get("url"):
                evidence_urls.append(item["url"])

    evidence_text = "\n".join(evidence_parts) if evidence_parts else "No relevant news articles found."

    # Step 2: Call Claude to judge
    timeframe_note = f"\nPredicted timeframe: {prediction.predicted_timeframe}" if prediction.predicted_timeframe else ""
    examples_block = _build_examples_block(calibration_examples or [])
    today_str = datetime.utcnow().strftime("%B %-d, %Y")
    user_message = f"""Please evaluate the following prediction:

**Prediction**: "{prediction.prediction_text}"
**Predicted event**: {prediction.predicted_event or 'Not specified'}{timeframe_note}

**Evidence from news sources**:
{evidence_text}

{examples_block}

Rate this prediction's accuracy based on the evidence above.

Today's date: {today_str}"""

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        logger.error(f"LLM call failed for prediction {prediction.id}: {exc}")
        return None

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1]) if len(lines) > 2 else raw_text

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse judge response for prediction {prediction.id}: {exc}\nRaw: {raw_text[:500]}")
        return None

    rating_str = result.get("rating", "unresolved")
    try:
        llm_rating = RatingValue(rating_str)
    except ValueError:
        logger.warning(f"Unknown rating value '{rating_str}', defaulting to unresolved.")
        llm_rating = RatingValue.unresolved

    llm_reasoning = result.get("reasoning", "")
    if result.get("evidence_summary"):
        llm_reasoning = f"{llm_reasoning}\n\nEvidence summary: {result['evidence_summary']}"

    # Decide whether to auto-finalize or flag for human review.
    # Flag when the rating is nuanced (somewhat_true / mostly_untrue) OR when
    # the LLM made a definitive call (true / untrue) without supporting evidence.
    has_evidence = bool(evidence_urls)
    needs_review = (
        llm_rating in (RatingValue.somewhat_true, RatingValue.mostly_untrue)
        or (llm_rating in (RatingValue.true, RatingValue.untrue) and not has_evidence)
    )
    auto_finalized = not needs_review

    # Create or update the outcome
    if existing:
        existing.llm_rating = llm_rating
        existing.llm_reasoning = llm_reasoning
        existing.evidence_text = evidence_text
        existing.evidence_urls = json.dumps(evidence_urls)
        existing.judged_at = datetime.utcnow()
        if auto_finalized:
            existing.human_rating = llm_rating
            existing.is_finalized = True
        outcome = existing
    else:
        outcome = PredictionOutcome(
            prediction_id=prediction.id,
            evidence_text=evidence_text,
            evidence_urls=json.dumps(evidence_urls),
            llm_rating=llm_rating,
            llm_reasoning=llm_reasoning,
            human_rating=llm_rating if auto_finalized else None,
            is_finalized=auto_finalized,
            judged_at=datetime.utcnow(),
        )
        db.add(outcome)

    try:
        db.commit()
        db.refresh(outcome)
    except Exception as exc:
        db.rollback()
        logger.error(f"Error saving outcome for prediction {prediction.id}: {exc}")
        return None

    logger.info(f"Judged prediction {prediction.id}: {llm_rating.value}")
    return outcome
