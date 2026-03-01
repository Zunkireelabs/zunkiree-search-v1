import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.query import get_query_service
from app.services.verification import (
    get_or_create_session,
    handle_email_submission,
    handle_code_verification,
    handle_post_verification,
    handle_name_submission,
    handle_custom_field_submission,
    lookup_user_profile,
    looks_like_email,
    looks_like_code,
)
from app.services.personalization import classify_query, parse_lead_intents, _is_registration_query
from app.config import get_settings

logger = logging.getLogger("zunkiree.query.api")

router = APIRouter(prefix="/query", tags=["query"])
settings = get_settings()

GREETING_WORDS = {
    "hi", "hello", "hey", "yo",
    "good morning", "good afternoon",
    "good evening", "hola",
}


class QueryRequest(BaseModel):
    site_id: str = Field(..., description="Customer site identifier")
    question: str = Field(..., max_length=500, description="User question")
    session_id: str | None = Field(None, description="Session identifier for identity verification")


class SourceInfo(BaseModel):
    title: str
    url: str


class QueryResponse(BaseModel):
    answer: str
    suggestions: list[str] = []
    sources: list[SourceInfo] = []
    session_id: str | None = None


@router.post("", response_model=QueryResponse)
async def submit_query(
    request: Request,
    query: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a question and receive an AI-generated answer.

    The answer is generated using RAG (Retrieval-Augmented Generation)
    based on the customer's indexed data.
    """
    # [TEMP-LOG] Log incoming request
    logger.warning("[QUERY-TRACE] site_id=%s question=%r origin=%s", query.site_id, query.question[:80], request.headers.get("origin"))

    # Validate: reject empty questions
    if not query.question or not query.question.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_QUESTION", "message": "Question cannot be empty"},
        )

    query_service = get_query_service()

    # Resolve tenant FIRST — greeting needs tenant context
    try:
        customer = await query_service._get_customer(db, query.site_id)
        if not customer:
            raise ValueError("Invalid site_id")
        config = await query_service._get_widget_config(db, customer.id)
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_SITE_ID", "message": str(e)},
        )

    brand_name = config.brand_name if config else customer.name

    # Handle greeting intent AFTER tenant resolution
    cleaned = query.question.lower().strip()
    if cleaned in GREETING_WORDS:
        # Use config quick_actions for greeting suggestions
        suggestions: list[str] = []
        if config and config.quick_actions:
            try:
                suggestions = json.loads(config.quick_actions)
            except (json.JSONDecodeError, TypeError):
                suggestions = []

        return QueryResponse(
            answer=f"Hi! I'm {brand_name}. How can I help you today?",
            suggestions=suggestions,
            sources=[],
            session_id=query.session_id,
        )

    # --- Identity verification + lead capture pre-processing ---
    user_email: str | None = None
    user_profile_dict: dict | None = None
    welcome_prefix: str | None = None
    verification_enabled = config and config.enable_identity_verification
    lead_intents_config = parse_lead_intents(config.lead_intents) if config else []
    has_lead_intents = bool(lead_intents_config)
    question_to_answer = query.question.strip()
    lead_signup_cta = False

    is_reg_query = _is_registration_query(question_to_answer)
    if (verification_enabled or has_lead_intents or is_reg_query) and query.session_id:
        v_session = await get_or_create_session(db, query.session_id, customer.id)

        # State: code_sent — expect a 6-digit code
        if v_session.state == "code_sent":
            if looks_like_code(question_to_answer):
                code_ok, message = await handle_code_verification(db, v_session, question_to_answer)
                if code_ok:
                    # Code correct — check if returning or new user
                    post_msg, profile = await handle_post_verification(db, v_session)
                    if profile:
                        # Returning user — check if lead intent has missing fields
                        if v_session.detected_intent and v_session.intent_signup_fields:
                            intent_fields = json.loads(v_session.intent_signup_fields)
                            existing_custom = {}
                            if profile.custom_fields:
                                try:
                                    existing_custom = json.loads(profile.custom_fields)
                                except (json.JSONDecodeError, TypeError):
                                    existing_custom = {}
                            missing_fields = [
                                f for f in intent_fields
                                if f.get("key") not in existing_custom
                            ]
                            if missing_fields:
                                # Need to collect missing intent fields
                                v_session.state = "fields_requested"
                                v_session.verified_at = None  # undo premature verified_at from handle_post_verification
                                v_session.intent_signup_fields = json.dumps(missing_fields)
                                v_session.pending_custom_fields = json.dumps(existing_custom)
                                v_session.current_field_index = 0
                                v_session.user_name = profile.name
                                await db.commit()
                                first_field = missing_fields[0]
                                label = first_field.get("label", first_field.get("key", "field"))
                                return QueryResponse(
                                    answer=f"Welcome back, {profile.name}! I have a few quick questions to personalize your experience.\n\n{label}",
                                    suggestions=[],
                                    sources=[],
                                    session_id=query.session_id,
                                )
                        # No missing fields — answer the pending question
                        user_email = v_session.email
                        user_profile_dict = _profile_to_dict(profile)
                        welcome_prefix = post_msg
                        question_to_answer = v_session.pending_question or question_to_answer
                    else:
                        # New user — ask for name to sign up
                        return QueryResponse(
                            answer=f"Looks like you're new here! Let's get you signed up.\n\n{post_msg}",
                            suggestions=[],
                            sources=[],
                            session_id=query.session_id,
                        )
                else:
                    # Wrong code — return error message
                    return QueryResponse(
                        answer=message,
                        suggestions=[],
                        sources=[],
                        session_id=query.session_id,
                    )
            else:
                # Not a code — re-prompt
                return QueryResponse(
                    answer=f"I've sent a verification code to {v_session.email}. Please enter the 6-digit code to continue.",
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )

        # State: name_requested — user is submitting their name
        elif v_session.state == "name_requested":
            msg, profile = await handle_name_submission(db, v_session, question_to_answer)
            if profile:
                # No custom fields — profile created, answer pending question
                user_email = v_session.email
                user_profile_dict = _profile_to_dict(profile)
                welcome_prefix = f"Welcome, {profile.name}!"
                question_to_answer = v_session.pending_question or question_to_answer
            else:
                # Custom fields needed — ask first field
                return QueryResponse(
                    answer=msg,
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )

        # State: fields_requested — user is submitting a custom field value
        elif v_session.state == "fields_requested":
            msg, profile = await handle_custom_field_submission(db, v_session, question_to_answer)
            if profile:
                # All fields collected — profile created/updated, answer pending question
                user_email = v_session.email
                user_profile_dict = _profile_to_dict(profile)
                welcome_prefix = f"Welcome, {profile.name}!"
                question_to_answer = v_session.pending_question or question_to_answer
            else:
                # More fields to collect
                return QueryResponse(
                    answer=msg,
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )

        # State: email_requested — waiting for email
        elif v_session.state == "email_requested":
            if looks_like_email(question_to_answer):
                message = await handle_email_submission(db, v_session, question_to_answer.strip(), brand_name)
                return QueryResponse(
                    answer=message,
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )
            else:
                # Not an email — re-prompt (this state is for queries needing identity)
                return QueryResponse(
                    answer=(
                        "I'd love to help with that! To access your personalized information, "
                        "please enter your email address to verify your identity."
                    ),
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )

        # State: anonymous — classify query as general/personal/lead
        elif v_session.state == "anonymous":
            # If user responds to lead CTA with their email, start verification
            if looks_like_email(question_to_answer) and v_session.pending_question:
                message = await handle_email_submission(db, v_session, question_to_answer.strip(), brand_name)
                return QueryResponse(
                    answer=message,
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )

            classification = await classify_query(question_to_answer, lead_intents_config or None)

            if classification["type"] == "lead":
                # Lead intent — answer first via RAG, then prompt signup
                v_session.pending_question = question_to_answer
                v_session.detected_intent = classification["intent"]
                v_session.intent_signup_fields = json.dumps(classification.get("signup_fields", []))
                await db.commit()
                lead_signup_cta = True
                # Fall through to RAG — answer first, CTA appended after
            elif classification["type"] == "personal":
                is_reg = _is_registration_query(question_to_answer)
                if is_reg:
                    # Registration intent — answer first via RAG, then prompt signup
                    v_session.pending_question = question_to_answer
                    await db.commit()
                    lead_signup_cta = True
                    # Fall through to RAG
                elif verification_enabled:
                    # Truly personal query requiring identity (e.g., "show my grades")
                    v_session.pending_question = question_to_answer
                    v_session.state = "email_requested"
                    await db.commit()
                    return QueryResponse(
                        answer=(
                            "I can help you with that! To access your personalized information, "
                            "I'll need to verify your identity.\n\n"
                            "Please enter your email address to log in. "
                            "If you don't have an account yet, we'll get you signed up."
                        ),
                        suggestions=[],
                        sources=[],
                        session_id=query.session_id,
                    )
                # else: general personal query without verification — fall through to RAG

            # Expand short follow-up queries with pending lead context
            if not lead_signup_cta and v_session.pending_question and len(question_to_answer.split()) <= 4:
                question_to_answer = f"{v_session.pending_question} - {question_to_answer}"
                lead_signup_cta = True

        # State: verified — pass email + profile through for personalized results
        elif v_session.state == "verified":
            user_email = v_session.email
            profile = await lookup_user_profile(db, customer.id, v_session.email)
            if profile:
                user_profile_dict = _profile_to_dict(profile)

    # Get request metadata
    origin = request.headers.get("origin")
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    try:
        result = await query_service.process_query(
            db=db,
            site_id=query.site_id,
            question=question_to_answer,
            origin=origin,
            user_agent=user_agent,
            ip_address=ip_address,
            user_email=user_email,
            user_profile=user_profile_dict,
        )

        answer = result["answer"]
        if welcome_prefix:
            answer = f"{welcome_prefix} {answer}"
        if lead_signup_cta:
            answer += "\n\nWant our team to reach out and help you further? Just share your email address!"

        return QueryResponse(
            answer=answer,
            suggestions=result["suggestions"],
            sources=[SourceInfo(**s) for s in result["sources"]],
            session_id=query.session_id,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_SITE_ID", "message": str(e)},
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail={"code": "INVALID_ORIGIN", "message": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "An error occurred processing your request"},
        )


def _profile_to_dict(profile) -> dict:
    """Convert a UserProfile ORM object to a dict for the LLM."""
    import json as _json
    custom = None
    if profile.custom_fields:
        try:
            custom = _json.loads(profile.custom_fields)
        except (ValueError, TypeError):
            custom = None
    return {
        "name": profile.name,
        "email": profile.email,
        "custom_fields": custom,
        "user_type": getattr(profile, "user_type", None),
        "lead_intent": getattr(profile, "lead_intent", None),
    }
