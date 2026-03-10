import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Customer, QueryLog, DocumentChunk, WidgetConfig
from app.services.query import get_query_service
from app.services.verification import (
    get_or_create_session,
    handle_email_submission,
    handle_code_verification,
    handle_post_verification,
    handle_name_submission,
    handle_phone_submission,
    handle_location_submission,
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


import re

# Pattern to detect PII in query log entries — these should NEVER appear in autocomplete
_PII_PATTERNS = [
    re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+'),           # email
    re.compile(r'\b\d{6,}\b'),                          # phone numbers / verification codes (6+ digits)
    re.compile(r'\b\d{3}[-.\s]?\d{3,4}[-.\s]?\d{4}\b'),# formatted phone
    re.compile(r'^\d+$'),                                # pure numbers
]

def _looks_like_pii(text: str) -> bool:
    """Check if a query looks like personal data rather than a real question."""
    t = text.strip().lower()
    # Too short to be a real question (likely a name, code, or single word)
    word_count = len(t.split())
    if word_count <= 2 and '?' not in t:
        return True
    # Contains email, phone, or digit patterns
    for pat in _PII_PATTERNS:
        if pat.search(t):
            return True
    return False


@router.get("/autocomplete")
async def autocomplete(
    site_id: str = Query(..., description="Customer site identifier"),
    q: str = Query(..., min_length=2, max_length=200, description="Search prefix"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return autocomplete suggestions based on popular past queries and document titles.
    Only returns genuine questions — never personal data (names, emails, phones, etc.).
    """
    # Resolve customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == site_id, Customer.is_active == True)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return {"suggestions": []}

    q_lower = q.strip().lower()
    suggestions: list[str] = []
    seen = set()

    # 1. Popular past queries matching the prefix — heavily filtered to exclude PII
    #    Only include entries that look like real questions (3+ words, no PII patterns)
    query_result = await db.execute(
        text("""
            SELECT LOWER(TRIM(question)) AS q, COUNT(*) AS cnt
            FROM query_logs
            WHERE customer_id = :cid
              AND LOWER(question) LIKE :prefix
              AND LENGTH(TRIM(question)) > 15
              AND question NOT LIKE '%%@%%'
              AND question !~ '\\d{6,}'
              AND array_length(string_to_array(TRIM(question), ' '), 1) >= 3
            GROUP BY LOWER(TRIM(question))
            HAVING COUNT(*) >= 1
            ORDER BY cnt DESC
            LIMIT 15
        """),
        {"cid": str(customer.id), "prefix": f"{q_lower}%"},
    )
    for row in query_result.fetchall():
        text_val = row[0].strip()
        # Double-check with Python-side PII filter
        if text_val not in seen and text_val != q_lower and not _looks_like_pii(text_val):
            suggestions.append(text_val)
            seen.add(text_val)
            if len(suggestions) >= 5:
                break

    # 2. Document titles matching the prefix
    if len(suggestions) < 5:
        title_result = await db.execute(
            text("""
                SELECT DISTINCT source_title
                FROM document_chunks
                WHERE customer_id = :cid
                  AND LOWER(source_title) LIKE :prefix
                  AND source_title IS NOT NULL
                LIMIT :lim
            """),
            {"cid": str(customer.id), "prefix": f"%{q_lower}%", "lim": 5 - len(suggestions)},
        )
        for row in title_result.fetchall():
            title = row[0].strip()
            title_lower = title.lower()
            if title_lower not in seen:
                suggestions.append(title)
                seen.add(title_lower)

    # 3. Quick actions from widget config that match
    if len(suggestions) < 5:
        config_result = await db.execute(
            select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
        )
        config = config_result.scalar_one_or_none()
        if config and config.quick_actions:
            try:
                actions = json.loads(config.quick_actions)
                for action in actions:
                    if isinstance(action, str) and q_lower in action.lower() and action.lower() not in seen:
                        suggestions.append(action)
                        seen.add(action.lower())
                        if len(suggestions) >= 5:
                            break
            except (json.JSONDecodeError, TypeError):
                pass

    return {"suggestions": suggestions[:5]}


class QueryRequest(BaseModel):
    site_id: str = Field(..., description="Customer site identifier")
    question: str = Field(..., max_length=500, description="User question")
    session_id: str | None = Field(None, description="Session identifier for identity verification")
    language: str | None = Field(None, description="Response language code (e.g. 'en', 'ne')")


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
    """
    logger.warning("[QUERY-TRACE] site_id=%s question=%r origin=%s", query.site_id, query.question[:80], request.headers.get("origin"))

    if not query.question or not query.question.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_QUESTION", "message": "Question cannot be empty"},
        )

    query_service = get_query_service()

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

    # Handle greeting
    cleaned = query.question.lower().strip()
    if cleaned in GREETING_WORDS:
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

    # --- Identity verification + lead capture ---
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
                    post_msg, profile = await handle_post_verification(db, v_session)
                    if profile:
                        # Returning user — check for missing intent fields
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
                                v_session.state = "fields_requested"
                                v_session.verified_at = None
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
                        # Returning user, all info present — answer pending question
                        if not v_session.pending_question:
                            # No pending question — just welcome them back
                            return QueryResponse(
                                answer=f"Welcome back, {profile.name}! How can I help you today?",
                                suggestions=_get_quick_actions(config),
                                sources=[],
                                session_id=query.session_id,
                            )
                        user_email = v_session.email
                        user_profile_dict = _profile_to_dict(profile)
                        welcome_prefix = post_msg
                        question_to_answer = v_session.pending_question
                    else:
                        # New user — post_msg asks for full name
                        return QueryResponse(
                            answer=post_msg,
                            suggestions=[],
                            sources=[],
                            session_id=query.session_id,
                        )
                else:
                    return QueryResponse(
                        answer=message,
                        suggestions=[],
                        sources=[],
                        session_id=query.session_id,
                    )
            else:
                return QueryResponse(
                    answer=f"I've sent a verification code to {v_session.email}. Please enter the 6-digit code to continue.",
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )

        # State: name_requested — new user submitting full name
        elif v_session.state == "name_requested":
            msg, profile = await handle_name_submission(db, v_session, question_to_answer)
            if profile:
                return _signup_success_response(profile, query.session_id)
            else:
                return QueryResponse(answer=msg, suggestions=[], sources=[], session_id=query.session_id)

        # State: phone_requested — new user submitting phone
        elif v_session.state == "phone_requested":
            msg, profile = await handle_phone_submission(db, v_session, question_to_answer)
            if profile:
                return _signup_success_response(profile, query.session_id)
            else:
                return QueryResponse(answer=msg, suggestions=[], sources=[], session_id=query.session_id)

        # State: location_requested — new user submitting location
        elif v_session.state == "location_requested":
            msg, profile = await handle_location_submission(db, v_session, question_to_answer)
            if profile:
                return _signup_success_response(profile, query.session_id)
            else:
                return QueryResponse(answer=msg, suggestions=[], sources=[], session_id=query.session_id)

        # State: fields_requested — custom field value
        elif v_session.state == "fields_requested":
            msg, profile = await handle_custom_field_submission(db, v_session, question_to_answer)
            if profile:
                return _signup_success_response(profile, query.session_id)
            else:
                return QueryResponse(answer=msg, suggestions=[], sources=[], session_id=query.session_id)

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
                return QueryResponse(
                    answer=(
                        "I'd love to help with that! To access your personalized information, "
                        "please enter your email address to verify your identity."
                    ),
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )

        # State: anonymous — answer freely, capture lead after 6 questions or on login/signup intent
        elif v_session.state == "anonymous":
            # If user responds with their email (to our lead capture prompt or voluntarily)
            if looks_like_email(question_to_answer):
                if v_session.pending_question or v_session.question_count >= 6:
                    message = await handle_email_submission(db, v_session, question_to_answer.strip(), brand_name)
                    return QueryResponse(
                        answer=message,
                        suggestions=[],
                        sources=[],
                        session_id=query.session_id,
                    )

            # Check if this is a login/signup/status/registration query — ask for email immediately
            if is_reg_query or _is_registration_query(question_to_answer):
                v_session.pending_question = question_to_answer
                v_session.state = "email_requested"
                # Classify for intent fields
                if has_lead_intents:
                    classification = await classify_query(question_to_answer, lead_intents_config or None)
                    if classification["type"] == "lead":
                        v_session.detected_intent = classification["intent"]
                        v_session.intent_signup_fields = json.dumps(classification.get("signup_fields", []))
                await db.commit()
                return QueryResponse(
                    answer=(
                        "I can help you with that! Please enter your email address "
                        "so I can check your account or get you started."
                    ),
                    suggestions=[],
                    sources=[],
                    session_id=query.session_id,
                )

            # Increment question count
            v_session.question_count = (v_session.question_count or 0) + 1
            await db.commit()

            # After 6 questions — ask for email to capture lead
            if v_session.question_count >= 6 and (has_lead_intents or verification_enabled):
                lead_signup_cta = True

        # State: verified — pass through
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
            language=query.language,
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


@router.post("/stream")
async def submit_query_stream(
    request: Request,
    query: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a question and receive a streamed AI-generated answer via SSE.
    """
    logger.warning("[QUERY-STREAM] site_id=%s question=%r", query.site_id, query.question[:80])

    if not query.question or not query.question.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_QUESTION", "message": "Question cannot be empty"},
        )

    query_service = get_query_service()

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

    # Handle greeting — return immediately (no streaming needed)
    cleaned = query.question.lower().strip()
    if cleaned in GREETING_WORDS:
        suggestions: list[str] = []
        if config and config.quick_actions:
            try:
                suggestions = json.loads(config.quick_actions)
            except (json.JSONDecodeError, TypeError):
                suggestions = []

        async def greeting_stream():
            greeting = f"Hi! I'm {brand_name}. How can I help you today?"
            yield f"data: {json.dumps({'type': 'token', 'data': greeting})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'answer': greeting, 'suggestions': suggestions, 'sources': [], 'session_id': query.session_id})}\n\n"

        return StreamingResponse(greeting_stream(), media_type="text/event-stream")

    # --- Identity verification + lead capture (same logic as non-stream) ---
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

        # For verification states, return immediate SSE (no streaming LLM needed)
        immediate = await _handle_verification_for_stream(
            db, v_session, question_to_answer, query.session_id, config,
            brand_name, has_lead_intents, lead_intents_config, is_reg_query,
        )
        if immediate is not None:
            # immediate is either a QueryResponse or a dict with stream-through data
            if isinstance(immediate, QueryResponse):
                async def immediate_stream():
                    yield f"data: {json.dumps({'type': 'token', 'data': immediate.answer})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'answer': immediate.answer, 'suggestions': immediate.suggestions, 'sources': [], 'session_id': immediate.session_id})}\n\n"
                return StreamingResponse(immediate_stream(), media_type="text/event-stream")
            # dict means we should stream-through with enrichments
            user_email = immediate.get("user_email")
            user_profile_dict = immediate.get("user_profile")
            welcome_prefix = immediate.get("welcome_prefix")
            question_to_answer = immediate.get("question", question_to_answer)
            lead_signup_cta = immediate.get("lead_signup_cta", False)
        else:
            # anonymous state checks
            if v_session.state == "anonymous":
                if looks_like_email(question_to_answer):
                    if v_session.pending_question or v_session.question_count >= 6:
                        message = await handle_email_submission(db, v_session, question_to_answer.strip(), brand_name)
                        async def email_stream():
                            yield f"data: {json.dumps({'type': 'token', 'data': message})}\n\n"
                            yield f"data: {json.dumps({'type': 'done', 'answer': message, 'suggestions': [], 'sources': [], 'session_id': query.session_id})}\n\n"
                        return StreamingResponse(email_stream(), media_type="text/event-stream")

                if is_reg_query or _is_registration_query(question_to_answer):
                    v_session.pending_question = question_to_answer
                    v_session.state = "email_requested"
                    if has_lead_intents:
                        classification = await classify_query(question_to_answer, lead_intents_config or None)
                        if classification["type"] == "lead":
                            v_session.detected_intent = classification["intent"]
                            v_session.intent_signup_fields = json.dumps(classification.get("signup_fields", []))
                    await db.commit()
                    msg = "I can help you with that! Please enter your email address so I can check your account or get you started."
                    async def reg_stream():
                        yield f"data: {json.dumps({'type': 'token', 'data': msg})}\n\n"
                        yield f"data: {json.dumps({'type': 'done', 'answer': msg, 'suggestions': [], 'sources': [], 'session_id': query.session_id})}\n\n"
                    return StreamingResponse(reg_stream(), media_type="text/event-stream")

                v_session.question_count = (v_session.question_count or 0) + 1
                await db.commit()

                if v_session.question_count >= 6 and (has_lead_intents or verification_enabled):
                    lead_signup_cta = True

            elif v_session.state == "verified":
                user_email = v_session.email
                profile = await lookup_user_profile(db, customer.id, v_session.email)
                if profile:
                    user_profile_dict = _profile_to_dict(profile)

    origin = request.headers.get("origin")
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    async def event_stream():
        prefix_sent = False
        try:
            if welcome_prefix:
                yield f"data: {json.dumps({'type': 'token', 'data': welcome_prefix + ' '})}\n\n"
                prefix_sent = True
            async for event in query_service.process_query_stream(
                db=db,
                site_id=query.site_id,
                question=question_to_answer,
                origin=origin,
                user_agent=user_agent,
                ip_address=ip_address,
                user_email=user_email,
                user_profile=user_profile_dict,
                language=query.language,
            ):
                if event["type"] == "token":
                    yield f"data: {json.dumps({'type': 'token', 'data': event['data']})}\n\n"
                elif event["type"] == "done":
                    answer = event["answer"]
                    if lead_signup_cta:
                        answer += "\n\nWant our team to reach out and help you further? Just share your email address!"
                    yield f"data: {json.dumps({'type': 'done', 'answer': answer, 'suggestions': event.get('suggestions', []), 'sources': event.get('sources', []), 'session_id': query.session_id})}\n\n"
                elif event["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': event['message']})}\n\n"
        except Exception as e:
            logger.exception("[QUERY-STREAM] Error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred processing your request'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _handle_verification_for_stream(
    db, v_session, question_to_answer, session_id, config,
    brand_name, has_lead_intents, lead_intents_config, is_reg_query,
):
    """
    Handle verification states for the streaming endpoint.
    Returns:
    - QueryResponse for immediate responses (verification prompts, signup success)
    - dict for stream-through with enrichments (verified user with pending question)
    - None to fall through to anonymous/verified state handling
    """
    if v_session.state == "code_sent":
        if looks_like_code(question_to_answer):
            code_ok, message = await handle_code_verification(db, v_session, question_to_answer)
            if code_ok:
                post_msg, profile = await handle_post_verification(db, v_session)
                if profile:
                    if v_session.detected_intent and v_session.intent_signup_fields:
                        intent_fields = json.loads(v_session.intent_signup_fields)
                        existing_custom = {}
                        if profile.custom_fields:
                            try:
                                existing_custom = json.loads(profile.custom_fields)
                            except (json.JSONDecodeError, TypeError):
                                existing_custom = {}
                        missing_fields = [f for f in intent_fields if f.get("key") not in existing_custom]
                        if missing_fields:
                            v_session.state = "fields_requested"
                            v_session.verified_at = None
                            v_session.intent_signup_fields = json.dumps(missing_fields)
                            v_session.pending_custom_fields = json.dumps(existing_custom)
                            v_session.current_field_index = 0
                            v_session.user_name = profile.name
                            await db.commit()
                            first_field = missing_fields[0]
                            label = first_field.get("label", first_field.get("key", "field"))
                            return QueryResponse(
                                answer=f"Welcome back, {profile.name}! I have a few quick questions to personalize your experience.\n\n{label}",
                                suggestions=[], sources=[], session_id=session_id,
                            )
                    if not v_session.pending_question:
                        return QueryResponse(
                            answer=f"Welcome back, {profile.name}! How can I help you today?",
                            suggestions=_get_quick_actions(config), sources=[], session_id=session_id,
                        )
                    return {
                        "user_email": v_session.email,
                        "user_profile": _profile_to_dict(profile),
                        "welcome_prefix": post_msg,
                        "question": v_session.pending_question,
                    }
                else:
                    return QueryResponse(answer=post_msg, suggestions=[], sources=[], session_id=session_id)
            else:
                return QueryResponse(answer=message, suggestions=[], sources=[], session_id=session_id)
        else:
            return QueryResponse(
                answer=f"I've sent a verification code to {v_session.email}. Please enter the 6-digit code to continue.",
                suggestions=[], sources=[], session_id=session_id,
            )

    elif v_session.state == "name_requested":
        msg, profile = await handle_name_submission(db, v_session, question_to_answer)
        if profile:
            return _signup_success_response(profile, session_id)
        return QueryResponse(answer=msg, suggestions=[], sources=[], session_id=session_id)

    elif v_session.state == "phone_requested":
        msg, profile = await handle_phone_submission(db, v_session, question_to_answer)
        if profile:
            return _signup_success_response(profile, session_id)
        return QueryResponse(answer=msg, suggestions=[], sources=[], session_id=session_id)

    elif v_session.state == "location_requested":
        msg, profile = await handle_location_submission(db, v_session, question_to_answer)
        if profile:
            return _signup_success_response(profile, session_id)
        return QueryResponse(answer=msg, suggestions=[], sources=[], session_id=session_id)

    elif v_session.state == "fields_requested":
        msg, profile = await handle_custom_field_submission(db, v_session, question_to_answer)
        if profile:
            return _signup_success_response(profile, session_id)
        return QueryResponse(answer=msg, suggestions=[], sources=[], session_id=session_id)

    elif v_session.state == "email_requested":
        if looks_like_email(question_to_answer):
            message = await handle_email_submission(db, v_session, question_to_answer.strip(), brand_name)
            return QueryResponse(answer=message, suggestions=[], sources=[], session_id=session_id)
        else:
            return QueryResponse(
                answer="I'd love to help with that! To access your personalized information, please enter your email address to verify your identity.",
                suggestions=[], sources=[], session_id=session_id,
            )

    # anonymous or verified — fall through
    return None


def _get_quick_actions(config) -> list[str]:
    """Extract quick action suggestions from widget config."""
    if config and config.quick_actions:
        try:
            return json.loads(config.quick_actions)
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _signup_success_response(profile, session_id: str | None) -> QueryResponse:
    """Return a signup success message instead of going to RAG."""
    return QueryResponse(
        answer=(
            f"You're all set, {profile.name}! Your sign up is complete.\n\n"
            f"How can I help you today?"
        ),
        suggestions=[],
        sources=[],
        session_id=session_id,
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
        "phone": getattr(profile, "phone", None),
        "location": getattr(profile, "location", None),
        "custom_fields": custom,
        "user_type": getattr(profile, "user_type", None),
        "lead_intent": getattr(profile, "lead_intent", None),
    }
