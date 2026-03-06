import json
import re
import secrets
import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.verification import VerificationSession
from app.models.user_profile import UserProfile
from app.models.widget_config import WidgetConfig
from app.services.email import send_verification_email

logger = logging.getLogger("zunkiree.verification")

MAX_CODE_ATTEMPTS = 3
CODE_EXPIRY_MINUTES = 10

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


async def get_or_create_session(
    db: AsyncSession, session_id: str, customer_id
) -> VerificationSession:
    """Find an existing verification session or create a new one."""
    result = await db.execute(
        select(VerificationSession).where(
            VerificationSession.session_id == session_id
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        session = VerificationSession(
            session_id=session_id,
            customer_id=customer_id,
            state="anonymous",
        )
        db.add(session)
        await db.commit()

    return session


async def handle_email_submission(
    db: AsyncSession,
    session: VerificationSession,
    email: str,
    brand_name: str,
) -> str:
    """Process an email submission: generate code, send email, update state."""
    code = f"{secrets.randbelow(900000) + 100000}"

    session.email = email
    session.verification_code = code
    session.code_expires_at = datetime.utcnow() + timedelta(minutes=CODE_EXPIRY_MINUTES)
    session.code_attempts = 0
    session.state = "code_sent"
    await db.commit()

    await send_verification_email(email, code, brand_name)

    logger.info("[VERIFY] Code sent to %s for session %s", email, session.session_id)
    return f"I've sent a 6-digit verification code to {email}. Please enter the code."


async def handle_code_verification(
    db: AsyncSession,
    session: VerificationSession,
    code_input: str,
) -> tuple[bool, str]:
    """
    Validate the verification code.
    Returns (code_correct, message).
    """
    # Check expiry
    if session.code_expires_at and datetime.utcnow() > session.code_expires_at:
        session.state = "email_requested"
        session.verification_code = None
        session.code_attempts = 0
        await db.commit()
        return False, "Your verification code has expired. Please enter your email address again."

    # Check attempts
    session.code_attempts += 1
    await db.commit()

    if session.code_attempts > MAX_CODE_ATTEMPTS:
        session.state = "email_requested"
        session.verification_code = None
        session.code_attempts = 0
        await db.commit()
        return False, "Too many incorrect attempts. Please enter your email address again."

    # Validate code
    if code_input.strip() == session.verification_code:
        session.verification_code = None
        await db.commit()
        logger.info("[VERIFY] Code correct for session %s (%s)", session.session_id, session.email)
        return True, "code_correct"

    remaining = MAX_CODE_ATTEMPTS - session.code_attempts
    if remaining <= 0:
        session.state = "email_requested"
        session.verification_code = None
        session.code_attempts = 0
        await db.commit()
        return False, "Incorrect code. No attempts remaining. Please enter your email address again."
    return False, f"Incorrect code. You have {remaining} attempt{'s' if remaining != 1 else ''} remaining."


async def handle_post_verification(
    db: AsyncSession,
    session: VerificationSession,
) -> tuple[str, UserProfile | None]:
    """
    After code is verified, check if user exists:
    - Returning user → verified, welcome back
    - New user → name_requested (start signup: name → phone → location → fields)
    """
    profile = await lookup_user_profile(db, session.customer_id, session.email)

    if profile:
        # Returning user — go straight to verified
        session.state = "verified"
        session.verified_at = datetime.utcnow()
        session.user_name = profile.name
        await db.commit()
        logger.info("[VERIFY] Returning user %s (%s)", profile.name, session.email)
        return f"Welcome back, {profile.name}!", profile

    # New user — ask for full name
    session.state = "name_requested"
    await db.commit()
    logger.info("[VERIFY] New user signup started for %s", session.email)
    return "Looks like you're new here! Let's get you signed up.\n\nWhat's your full name?", None


async def handle_name_submission(
    db: AsyncSession,
    session: VerificationSession,
    name: str,
) -> tuple[str, UserProfile | None]:
    """Process name submission. Move to phone_requested."""
    session.user_name = name.strip()
    session.state = "phone_requested"
    session.pending_custom_fields = json.dumps({})
    await db.commit()
    logger.info("[VERIFY] Name collected: %s, asking for phone", name.strip())
    return "What's your mobile number?", None


async def handle_phone_submission(
    db: AsyncSession,
    session: VerificationSession,
    phone: str,
) -> tuple[str, UserProfile | None]:
    """Process phone submission. Move to location_requested."""
    collected = json.loads(session.pending_custom_fields or "{}")
    collected["_phone"] = phone.strip()
    session.pending_custom_fields = json.dumps(collected)
    session.state = "location_requested"
    await db.commit()
    logger.info("[VERIFY] Phone collected for session %s", session.session_id)
    return "What's your location?", None


async def handle_location_submission(
    db: AsyncSession,
    session: VerificationSession,
    location: str,
) -> tuple[str, UserProfile | None]:
    """
    Process location submission.
    If business-specific fields exist → fields_requested.
    Otherwise → create profile and verify.
    """
    collected = json.loads(session.pending_custom_fields or "{}")
    collected["_location"] = location.strip()
    session.pending_custom_fields = json.dumps(collected)

    # Check for business-specific fields
    custom_fields = _get_intent_fields(session) or await _get_custom_fields_config(db, session.customer_id)

    if custom_fields:
        session.state = "fields_requested"
        session.current_field_index = 0
        await db.commit()
        field = custom_fields[0]
        label = field.get("label", field.get("key", "field"))
        return label, None

    # No custom fields — create profile
    return None, await _finalize_profile(db, session, collected)


async def handle_custom_field_submission(
    db: AsyncSession,
    session: VerificationSession,
    value: str,
) -> tuple[str, UserProfile | None]:
    """
    Process a custom field value submission.
    If more fields remain → ask next field.
    If last field → create profile and verify.
    """
    custom_fields = _get_intent_fields(session) or await _get_custom_fields_config(db, session.customer_id)
    collected = json.loads(session.pending_custom_fields or "{}")

    if not custom_fields:
        return None, await _finalize_profile(db, session, collected)

    # Store current field value
    current_idx = session.current_field_index or 0
    current_field = custom_fields[current_idx]
    field_key = current_field.get("key", f"field_{current_idx}")
    collected[field_key] = value.strip()
    session.pending_custom_fields = json.dumps(collected)

    # Check if more fields remain
    next_idx = current_idx + 1
    if next_idx < len(custom_fields):
        session.current_field_index = next_idx
        await db.commit()
        next_field = custom_fields[next_idx]
        label = next_field.get("label", next_field.get("key", "field"))
        return label, None

    # All fields collected — create profile
    return None, await _finalize_profile(db, session, collected)


async def _finalize_profile(
    db: AsyncSession,
    session: VerificationSession,
    collected: dict,
) -> UserProfile:
    """Extract phone/location from collected, create/update profile, mark verified."""
    phone = collected.pop("_phone", None)
    location = collected.pop("_location", None)
    clean_custom = {k: v for k, v in collected.items() if not k.startswith("_")}

    profile = await _upsert_user_profile(
        db, session.customer_id, session.email, session.user_name, clean_custom,
        user_type=session.detected_intent,
        lead_intent=session.detected_intent,
        phone=phone,
        location=location,
    )
    session.state = "verified"
    session.verified_at = datetime.utcnow()
    await db.commit()
    return profile


async def lookup_user_profile(
    db: AsyncSession, customer_id, email: str
) -> UserProfile | None:
    """Look up an existing user profile by customer + email."""
    result = await db.execute(
        select(UserProfile).where(
            UserProfile.customer_id == customer_id,
            UserProfile.email == email,
        )
    )
    return result.scalar_one_or_none()


async def _create_user_profile(
    db: AsyncSession,
    customer_id,
    email: str,
    name: str,
    custom_fields: dict,
    user_type: str | None = None,
    lead_intent: str | None = None,
    phone: str | None = None,
    location: str | None = None,
) -> UserProfile:
    """Create a new user profile."""
    profile = UserProfile(
        customer_id=customer_id,
        email=email,
        name=name,
        phone=phone,
        location=location,
        custom_fields=json.dumps(custom_fields) if custom_fields else None,
        user_type=user_type,
        lead_intent=lead_intent,
    )
    db.add(profile)
    await db.flush()
    return profile


async def _upsert_user_profile(
    db: AsyncSession,
    customer_id,
    email: str,
    name: str,
    custom_fields: dict,
    user_type: str | None = None,
    lead_intent: str | None = None,
    phone: str | None = None,
    location: str | None = None,
) -> UserProfile:
    """Create a new user profile, or update an existing one."""
    existing = await lookup_user_profile(db, customer_id, email)
    if existing:
        old_custom = {}
        if existing.custom_fields:
            try:
                old_custom = json.loads(existing.custom_fields)
            except (json.JSONDecodeError, TypeError):
                old_custom = {}
        merged = {**old_custom, **custom_fields}
        existing.custom_fields = json.dumps(merged) if merged else existing.custom_fields
        if user_type:
            existing.user_type = existing.user_type or user_type
        if lead_intent:
            existing.lead_intent = existing.lead_intent or lead_intent
        if phone:
            existing.phone = phone
        if location:
            existing.location = location
        await db.flush()
        logger.info("[VERIFY] Existing user updated: %s (%s)", existing.name, email)
        return existing
    return await _create_user_profile(
        db, customer_id, email, name, custom_fields,
        user_type=user_type, lead_intent=lead_intent,
        phone=phone, location=location,
    )


def _get_intent_fields(session: VerificationSession) -> list[dict]:
    """Get intent-specific signup fields from the session, if any."""
    if not session.intent_signup_fields:
        return []
    try:
        fields = json.loads(session.intent_signup_fields)
        return fields if isinstance(fields, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def get_lead_intents_config(
    db: AsyncSession, customer_id
) -> list[dict]:
    """Load the tenant's lead_intents JSON from widget config."""
    result = await db.execute(
        select(WidgetConfig.lead_intents).where(
            WidgetConfig.customer_id == customer_id
        )
    )
    raw = result.scalar_one_or_none()
    if not raw:
        return []
    try:
        intents = json.loads(raw)
        return intents if isinstance(intents, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def _get_custom_fields_config(
    db: AsyncSession, customer_id
) -> list[dict]:
    """Get the tenant's custom signup fields configuration."""
    result = await db.execute(
        select(WidgetConfig.identity_custom_fields).where(
            WidgetConfig.customer_id == customer_id
        )
    )
    raw = result.scalar_one_or_none()
    if not raw:
        return []
    try:
        fields = json.loads(raw)
        return fields if isinstance(fields, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def looks_like_email(text: str) -> bool:
    """Check if the input looks like an email address."""
    return bool(EMAIL_REGEX.match(text.strip()))


def looks_like_code(text: str) -> bool:
    """Check if the input looks like a 6-digit verification code."""
    return bool(re.match(r"^\d{6}$", text.strip()))
