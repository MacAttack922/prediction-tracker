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

Your task is to extract predictions about EXTERNAL, REAL-WORLD events — that is, claims about what will happen in the world: markets, economies, politics, geopolitics, companies, commodities, currencies, interest rates, elections, wars, recessions, etc.

Only extract predictions that have ALL THREE of the following:
1. A specific claim (not just vague sentiment)
2. An implied or explicit timeframe
3. A falsifiable outcome (can be rated true or false after the fact)

If a statement is too vague to rate true or false, do not extract it.

Focus on:
- Explicit forecasts about external events ("inflation will fall", "the Fed will cut rates", "X country will...")
- Market or economic predictions ("gold will hit $X", "stocks will drop", "the dollar will weaken")
- Political or geopolitical forecasts ("there will be a recession", "the election will go to...")

Do NOT extract:
- Personal goals, wishes, or aspirations ("I want to manage $1B one day", "I'd like to...")
- Career plans or personal ambitions
- General lifestyle opinions with no external event predicted
- Historical descriptions of past events
- Rhetorical questions or abstract philosophical musings
- Vague sentiment without a specific predicted outcome ("things will get worse", "markets will be volatile")
- Conditional predictions dependent on an external trigger ("if China invades Taiwan, oil will spike")
- Retrospective claims ("as I predicted, inflation came down")

Few-shot examples:
EXTRACT THIS: "I expect the Fed to cut rates at least twice before end of 2024" — specific claim, clear timeframe, falsifiable.
EXTRACT THIS: "Bitcoin will hit $200,000 by the end of this cycle" — specific asset, price target, timeframe implied.
DO NOT EXTRACT: "The Fed is going to have a really hard time here" — vague, no timeframe, not falsifiable.
DO NOT EXTRACT: "As I predicted, inflation came down" — retrospective, not forward-looking.
DO NOT EXTRACT: "Markets will be volatile" — too vague to rate true or false.
DO NOT EXTRACT: "If China invades Taiwan, oil prices will spike" — conditional, dependent on external trigger.

For each prediction, extract:
- prediction_text: The exact quote or very close paraphrase from the text
- predicted_event: A brief (1 sentence) description of the external event being predicted
- predicted_timeframe: The timeframe mentioned (e.g., "by end of 2024", "within 6 months"), or null if none
- target_date: Your best estimate of the target date as an ISO 8601 string (e.g. "2024-12-31"), or null if no date can be inferred. Use the end of the named period (e.g. "by end of 2024" → "2024-12-31", "by mid-2025" → "2025-06-30", "next year" relative to the source date → last day of that year).
- confidence_language: Any hedging or confidence words used (e.g., "I think", "certainly", "likely"), or null if none

Respond ONLY with a valid JSON array. If there are no qualifying predictions, respond with an empty array [].

Example response:
[
  {
    "prediction_text": "I think inflation will fall below 3% by mid-2024",
    "predicted_event": "Inflation falling below 3%",
    "predicted_timeframe": "by mid-2024",
    "target_date": "2024-06-30",
    "confidence_language": "I think"
  }
]"""

NEWS_EXTRACTION_SYSTEM_PROMPT = """You are an expert analyst specializing in identifying predictions and forecasts made by specific individuals.

You will be given a news article and the name of an analyst. Your task is to extract predictions about EXTERNAL, REAL-WORLD events that are directly attributed to that analyst — things they said, wrote, or were quoted as saying. Ignore predictions or claims made by journalists, other sources, or anyone other than the named analyst.

Only extract predictions that have ALL THREE of the following:
1. A specific claim (not just vague sentiment)
2. An implied or explicit timeframe
3. A falsifiable outcome (can be rated true or false after the fact)

If a statement is too vague to rate true or false, do not extract it.

Focus on:
- Direct quotes from the analyst forecasting external events (markets, economies, politics, geopolitics)
- Paraphrased statements attributed to the analyst with specific predictive content
- Explicit forecasts ("X will happen", "I expect Y to occur")

Do NOT extract:
- Statements made by journalists or other people
- The analyst's personal goals, wishes, or career aspirations
- Historical descriptions of past events
- Vague sentiment without a specific verifiable outcome ("markets will be volatile")
- General opinions with no external event predicted
- Conditional predictions dependent on an external trigger ("if X then Y")
- Retrospective claims ("as I predicted...")

Few-shot examples:
EXTRACT THIS: "I expect the Fed to cut rates at least twice before end of 2024" — specific claim, clear timeframe, falsifiable.
EXTRACT THIS: "Bitcoin will hit $200,000 by the end of this cycle" — specific asset, price target, timeframe implied.
DO NOT EXTRACT: "The Fed is going to have a really hard time here" — vague, no timeframe, not falsifiable.
DO NOT EXTRACT: "As I predicted, inflation came down" — retrospective, not forward-looking.
DO NOT EXTRACT: "Markets will be volatile" — too vague to rate true or false.
DO NOT EXTRACT: "If China invades Taiwan, oil prices will spike" — conditional, dependent on external trigger.

For each prediction, extract:
- prediction_text: The exact quote or close paraphrase attributed to the analyst
- predicted_event: A brief (1 sentence) description of the external event being predicted
- predicted_timeframe: The timeframe mentioned, or null if none
- target_date: Your best estimate of the target date as an ISO 8601 string (e.g. "2024-12-31"), or null if no date can be inferred.
- confidence_language: Hedging or confidence words used, or null if none

Respond ONLY with a valid JSON array. If there are no qualifying predictions attributed to the analyst, respond with an empty array []."""


# Signal type 1: forward-looking verbs
_FORWARD_VERBS = [
    "will ", "won't ", "wont ", "going to", "expect", "forecast", "predict",
    "projection", "anticipate", "i think", "i believe", "i suspect",
    "bet ", "odds are", "chances are", "likely", "probably",
]

# Signal type 2: timeframe markers
_TIMEFRAME_MARKERS = [
    "by 2025", "by 2026", "by 2027", "by 2028", "by 2029", "by 2030",
    "by 20", "within ", "before the", "next year", "this year",
    "next month", "next quarter", "over the next", "in the coming", "in the next",
    "q1 ", "q2 ", "q3 ", "q4 ", "end of", "by end", "by mid",
    "decade", " months", "years from now",
]

# Signal type 3: specific domain nouns
_DOMAIN_NOUNS = [
    "gdp", "recession", "inflation", "deflation", "bitcoin", "crypto",
    "fed ", "federal reserve", "market", "unemployment", "war ", "invasion",
    "collapse", "crash", "rate hike", "rate cut", "interest rate",
    "dollar", "oil ", "gold ", "china", "s&p", "economy", "debt", "default",
    "nasdaq", "dow ", "stock", "bond", "yield", "currency", "trade war",
    "election", "tariff", "housing",
]

# Phrases that indicate retrospective or non-predictive content — skip immediately
_NEGATIVE_SIGNALS = [
    "as i expected", "as i predicted", "as i said", "historically",
    "in the past", "used to ", "some analysts expect", "it remains to be seen",
    "i hope", "i wish", "i'd like to see", "i would like to see",
]

# Specificity scoring: minimum score of 2 required before LLM call
_SPECIFICITY_POSITIVE = [
    # Named assets / countries / metrics
    ("bitcoin", 1), ("btc", 1), ("ethereum", 1), ("s&p", 1), ("nasdaq", 1),
    ("dow ", 1), ("fed ", 1), ("federal reserve", 1), ("gdp", 1),
    ("inflation", 1), ("unemployment", 1), ("oil ", 1), ("gold ", 1),
    ("dollar", 1), ("china", 1), ("russia", 1), ("europe", 1), ("iran", 1),
    ("interest rate", 1), ("treasury", 1), ("yield", 1), ("housing", 1),
    ("recession", 1), ("debt", 1), ("tariff", 1), ("election", 1),
]
_SPECIFICITY_NUMERIC = [
    # Percentage or price targets
    ("%", 1), ("percent", 1), ("basis point", 1), ("$", 1),
    ("million", 1), ("billion", 1), ("trillion", 1),
]
_SPECIFICITY_TIMEFRAME = [
    # Named timeframes
    ("by end of", 1), ("by mid-", 1), ("by 20", 1), ("within ", 1),
    ("before the", 1), ("next year", 1), ("this year", 1),
    ("q1 ", 1), ("q2 ", 1), ("q3 ", 1), ("q4 ", 1),
    ("months", 1), ("years from now", 1), ("18 months", 1), ("decade", 1),
]
_SPECIFICITY_NEGATIVE = [
    # Conditional framing
    ("if ", -1), ("assuming ", -1), ("provided that", -1),
    # Vague magnitude
    ("significantly", -1), ("dramatically", -1), ("a lot", -1),
    ("massively", -1), ("hugely", -1), ("very much", -1),
]


def _has_prediction_signals(content: str) -> bool:
    """
    Require at least 2 of 3 signal types to be present:
    forward-looking verbs, timeframe markers, domain nouns.
    Also immediately reject content with negative signals.
    """
    lower = content.lower()

    # Reject if any negative signal is present
    if any(neg in lower for neg in _NEGATIVE_SIGNALS):
        return False

    hits = 0
    if any(s in lower for s in _FORWARD_VERBS):
        hits += 1
    if any(s in lower for s in _TIMEFRAME_MARKERS):
        hits += 1
    if any(s in lower for s in _DOMAIN_NOUNS):
        hits += 1

    return hits >= 2


def _specificity_score(content: str) -> int:
    """
    Score content for specificity. Returns an integer score.
    Minimum score of 2 required before sending to the LLM.
    """
    lower = content.lower()
    score = 0

    # +1 for named asset/country/metric (cap at 1 — presence is enough)
    if any(term in lower for term, _ in _SPECIFICITY_POSITIVE):
        score += 1

    # +1 for numeric figure (%, price, volume)
    if any(term in lower for term, _ in _SPECIFICITY_NUMERIC):
        score += 1

    # +1 for named timeframe
    if any(term in lower for term, _ in _SPECIFICITY_TIMEFRAME):
        score += 1

    # Penalties
    for term, penalty in _SPECIFICITY_NEGATIVE:
        if term in lower:
            score += penalty  # penalty is already negative

    return score


def extract_predictions(statement: "Statement", anthropic_client: "anthropic.Anthropic", db: Session) -> List[Prediction]:
    """Extract predictions from a statement using Claude and save them to the database."""
    if not statement.content or len(statement.content.strip()) < 50:
        logger.info(f"Statement {statement.id} too short, skipping extraction.")
        return None  # None = skipped

    if not _has_prediction_signals(statement.content):
        logger.info(f"Statement {statement.id} failed signal filter, skipping extraction.")
        return None  # None = skipped; [] = attempted but nothing found

    spec_score = _specificity_score(statement.content)
    if spec_score < 2:
        logger.info(f"Statement {statement.id} specificity score {spec_score} < 2, skipping extraction.")
        return None

    # Truncate very long content to avoid token limits
    content = statement.content[:8000] if len(statement.content) > 8000 else statement.content

    # For third-party content (news, guest videos, guest podcasts), use the quote-aware
    # prompt so we only extract predictions attributed to the named analyst, not the host.
    THIRD_PARTY_SOURCES = {"google_news", "youtube_guest", "podcast_guest", "cnbc", "fox_news", "bloomberg"}
    is_news = statement.source_type.value in THIRD_PARTY_SOURCES
    today_str = datetime.utcnow().strftime("%B %-d, %Y")
    if is_news:
        analyst_name = statement.analyst.name if statement.analyst else "the analyst"
        system_prompt = NEWS_EXTRACTION_SYSTEM_PROMPT
        user_message = f"""Analyst name: {analyst_name}

News article:
---
{content}
---

Extract only predictions directly attributed to {analyst_name}. Respond ONLY with a valid JSON array.

Today's date: {today_str}"""
    else:
        system_prompt = EXTRACTION_SYSTEM_PROMPT
        user_message = f"""Please extract all predictions from the following text:

---
{content}
---

Remember to respond ONLY with a valid JSON array.

Today's date: {today_str}"""

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

        # Parse target_date if the LLM provided one
        target_date = None
        raw_date = item.get("target_date") or None
        if raw_date:
            try:
                target_date = datetime.fromisoformat(str(raw_date).strip()[:10])
            except (ValueError, TypeError):
                pass

        prediction = Prediction(
            statement_id=statement.id,
            analyst_id=statement.analyst_id,
            prediction_text=prediction_text,
            predicted_event=item.get("predicted_event") or None,
            predicted_timeframe=item.get("predicted_timeframe") or None,
            target_date=target_date,
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
