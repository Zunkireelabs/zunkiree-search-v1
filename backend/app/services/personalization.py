import json
import logging
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger("zunkiree.personalization")

settings = get_settings()

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


_REGISTRATION_KEYWORDS = [
    "register", "registration", "sign up", "signup", "create account",
    "enroll", "enrollment", "enrolment", "want to join",
    "how to apply", "apply now", "get started",
    "i want to register", "i want to enroll", "i want to sign up",
]


def _is_registration_query(question: str) -> bool:
    """Fast keyword check for registration-intent queries."""
    q_lower = question.lower()
    return any(kw in q_lower for kw in _REGISTRATION_KEYWORDS)


def _keyword_match_intent(question: str, lead_intents: list[dict]) -> dict | None:
    """Fast keyword pre-screen against lead intents (no API call)."""
    q_lower = question.lower()
    for intent in lead_intents:
        keywords = intent.get("keywords", [])
        for kw in keywords:
            if kw.lower() in q_lower:
                return intent
    return None


async def classify_query(
    question: str, lead_intents: list[dict] | None = None
) -> dict:
    """
    Three-way query classifier.

    Returns one of:
      {"type": "general"}
      {"type": "personal"}
      {"type": "lead", "intent": "<intent_name>", "signup_fields": [...]}

    Process:
    1. Keyword pre-screen against lead_intents (no API call)
    2. If keyword match → confirm with LLM using tenant context
    3. Otherwise → personal/general classification (existing logic)
    """
    # Step 0: Registration-intent queries always require identity
    if _is_registration_query(question):
        logger.info("[CLASSIFY] question=%r type=personal (registration intent)", question[:60])
        return {"type": "personal"}

    # Step 1: Keyword pre-screen for lead intents
    if lead_intents:
        matched = _keyword_match_intent(question, lead_intents)
        if matched and matched.get("intent"):
            # Step 2: Confirm with LLM
            confirmed = await _confirm_lead_intent(question, matched)
            if confirmed:
                logger.info(
                    "[CLASSIFY] question=%r type=lead intent=%s",
                    question[:60], matched["intent"],
                )
                return {
                    "type": "lead",
                    "intent": matched["intent"],
                    "signup_fields": matched.get("signup_fields", []),
                }

    # Step 3: Fall back to personal/general classification
    is_personal = await _classify_personal_or_general(question)
    result_type = "personal" if is_personal else "general"
    logger.info("[CLASSIFY] question=%r type=%s", question[:60], result_type)
    return {"type": result_type}


async def _confirm_lead_intent(question: str, intent: dict) -> bool:
    """Use LLM to confirm a keyword-matched lead intent."""
    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a query intent classifier. A keyword match suggests this query "
                        f"relates to: \"{intent.get('description') or intent.get('intent', 'unknown')}\".\n"
                        "Determine if the user's message genuinely expresses this intent, "
                        "or if the keyword match is coincidental.\n"
                        "Reply with ONLY 'yes' or 'no'."
                    ),
                },
                {"role": "user", "content": question},
            ],
            max_tokens=5,
            temperature=0.0,
        )
        result = response.choices[0].message.content.strip().lower()
        return result == "yes"
    except Exception as e:
        logger.warning("[CLASSIFY] Lead intent confirmation failed: %s", e)
        # On failure, trust the keyword match
        return True


async def _classify_personal_or_general(question: str) -> bool:
    """Classify whether a question requires user identity to answer."""
    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the following user question as either 'personal' or 'general'.\n"
                        "A 'personal' question requires knowing who the user is OR expresses intent "
                        "to register, sign up, enroll, apply, or create an account "
                        "(e.g., 'What's my registration status?', 'Show my grades', 'I want to register', "
                        "'How do I sign up?', 'I want to enroll').\n"
                        "A 'general' question can be answered without user identity and does NOT express signup intent "
                        "(e.g., 'What are the admission requirements?', 'Where is the library?').\n"
                        "Reply with ONLY the word 'personal' or 'general'."
                    ),
                },
                {"role": "user", "content": question},
            ],
            max_tokens=10,
            temperature=0.0,
        )
        result = response.choices[0].message.content.strip().lower()
        return result == "personal"
    except Exception as e:
        logger.warning("[CLASSIFY] Personal/general classification failed: %s", e)
        return False


async def is_personalized_query(question: str) -> bool:
    """Backward-compatible wrapper around classify_query."""
    result = await classify_query(question)
    return result["type"] == "personal"


def parse_lead_intents(raw: str | None) -> list[dict]:
    """Parse lead_intents JSON string from widget config."""
    if not raw:
        return []
    try:
        intents = json.loads(raw)
        return intents if isinstance(intents, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
