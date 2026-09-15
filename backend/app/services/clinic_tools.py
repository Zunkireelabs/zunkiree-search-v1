"""
OpenAI function-calling tool definitions and executors for the ClinicAgentService
(website_type == "clinic"). See docs/stella+zunkireesearch/ZUNKIREE-CLINIC-AGENT-BRIEF.md
(brain folder) for the full spec.

Session state (pending/confirmed bookings) is in-memory, keyed by session_id.
A stage redeploy wipes it — same tradeoff as ConversationStore.
"""
import difflib
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.models.tenant_backend_credentials import TenantBackendCredentials
from app.services import clinic_availability as avail
from app.services.clinicmd_client import (
    ClinicMdError,
    ClinicMdNotConfigured,
    get_clinicmd_client,
    new_booking_id,
)

logger = logging.getLogger("zunkiree.clinic_tools")

NPT = ZoneInfo("Asia/Kathmandu")
DEFAULT_DIAL = "+977"
MAX_BARE_NATIONAL = 10


def to_e164(raw: str | None, fallback_dial: str = DEFAULT_DIAL) -> str | None:
    """Port of clinic-md/src/utils/phone.js toE164()."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    had_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    if had_plus:
        return f"+{digits}"
    fb_digits = re.sub(r"\D", "", fallback_dial or DEFAULT_DIAL) or "977"
    if len(digits) <= MAX_BARE_NATIONAL:
        return f"+{fb_digits}{digits}"
    return f"+{digits}"


CLINIC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search the clinic's knowledge base for general facts (hours, address, phone, parking, payment methods, doctors, policies). Do NOT use for prices/services/durations or open times — use list_services / check_availability for those.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What the visitor is asking about"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_services",
            "description": "List the clinic's treatments/services with price (NPR) and duration. This is the source of truth for prices — never guess prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional filter, e.g. 'cleaning' or 'whitening'"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check real open appointment times for a service. Omit date to get the next 3 open slots (one per day). Pass date (YYYY-MM-DD) for that day's open times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name, e.g. 'Teeth Cleaning'"},
                    "date": {"type": "string", "description": "YYYY-MM-DD, optional"},
                },
                "required": ["service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_booking",
            "description": "Validate a booking and stage it for confirmation. Creates nothing yet. Use the service_id/branch_id returned by list_services or check_availability. After calling this, read the returned summary back to the visitor and ask 'Shall I book this?' — only call confirm_booking after they explicitly say yes in a LATER message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_id": {"type": "string"},
                    "branch_id": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM, 24h"},
                    "full_name": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                    "note": {"type": "string", "description": "Any visitor note for the clinic"},
                },
                "required": ["service_id", "branch_id", "date", "time", "full_name", "phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_booking",
            "description": "Execute the previously prepared booking. Takes no arguments — only call after the visitor has explicitly confirmed the summary from prepare_booking in a message after that summary was shown.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

_SESSION_STATE: dict[str, dict] = {}
_ORG_CACHE: dict[str, dict] = {}


def _state(session_id: str) -> dict:
    return _SESSION_STATE.setdefault(session_id, {"pending": None, "confirmed": []})


def reset_session_state(session_id: str) -> None:
    """Test helper — clear in-memory state for a session."""
    _SESSION_STATE.pop(session_id, None)


def reset_org_cache() -> None:
    """Test helper — clear the org/branch cache."""
    _ORG_CACHE.clear()


async def execute_clinic_tool(
    tool_name: str,
    tool_args: dict,
    db: AsyncSession,
    customer: Customer,
    config: WidgetConfig | None,
    site_id: str,
    session_id: str,
    current_turn: int,
) -> dict:
    logger.info("[CLINIC-AGENT] tool=%s args=%s", tool_name, {k: v for k, v in tool_args.items() if k not in ("phone", "email", "full_name", "note")})
    try:
        if tool_name == "search_knowledge":
            return await _search_knowledge(db, customer, config, site_id, tool_args.get("query", ""))
        if tool_name == "list_services":
            return await _list_services(db, customer, tool_args.get("query"))
        if tool_name == "check_availability":
            return await _check_availability(db, customer, tool_args.get("service", ""), tool_args.get("date"))
        if tool_name == "prepare_booking":
            return await _prepare_booking(db, customer, session_id, current_turn, **tool_args)
        if tool_name == "confirm_booking":
            return await _confirm_booking(db, customer, session_id, current_turn)
        return {"error": f"Unknown tool: {tool_name}"}
    except ClinicMdNotConfigured:
        return {"error": "NOT_CONFIGURED", "message": "Booking system isn't connected right now — please call the clinic directly."}
    except ClinicMdError as e:
        logger.warning("[CLINIC-AGENT] tool=%s clinicmd_error pg_code=%s", tool_name, e.pg_code)
        return {"error": "CLINICMD_ERROR", "message": "I couldn't reach the booking system just now. Please try again shortly."}


# --- Knowledge ---

async def _search_knowledge(db: AsyncSession, customer: Customer, config: WidgetConfig | None, site_id: str, query: str) -> dict:
    if not query:
        return {"chunks": []}
    from app.services.query import get_query_service

    retrieval = await get_query_service()._retrieve_and_rank(db, customer, config, site_id, query)
    chunks = retrieval.get("chunks_for_llm") or []
    if not chunks:
        return {"chunks": [], "message": "Nothing found in the knowledge base for this."}
    return {"chunks": [{"content": c["content"]} for c in chunks[:4]]}


# --- Org / branch resolution ---

async def _resolve_org(db: AsyncSession, customer: Customer) -> tuple[str, list[dict]]:
    cached = _ORG_CACHE.get(customer.site_id)
    if cached:
        return cached["org_id"], cached["branches"]

    result = await db.execute(
        select(TenantBackendCredentials).where(
            TenantBackendCredentials.customer_id == customer.id,
            TenantBackendCredentials.backend_type == "clinicmd",
            TenantBackendCredentials.is_active == True,  # noqa: E712
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ClinicMdError("No ClinicMD org mapping configured for this tenant.", code="NOT_CONFIGURED")

    client = get_clinicmd_client()
    org = await client.get_org(row.remote_site_id)
    if not org:
        raise ClinicMdError(f"ClinicMD org '{row.remote_site_id}' not found or inactive.", code="ORG_NOT_FOUND")

    branches = await client.list_branches(org["id"])
    _ORG_CACHE[customer.site_id] = {"org_id": org["id"], "branches": branches}
    return org["id"], branches


def _default_branch(branches: list[dict]) -> dict | None:
    return branches[0] if branches else None


def _match_service(treatments: list[dict], service_name: str) -> tuple[dict | None, list[dict]]:
    """Fuzzy-resolve a service name. Returns (treatment, ambiguous_options)."""
    name_lower = service_name.lower().strip()
    exact = [t for t in treatments if t["name"].lower() == name_lower]
    if exact:
        return exact[0], []
    contains = [t for t in treatments if name_lower in t["name"].lower()]
    if len(contains) == 1:
        return contains[0], []
    if len(contains) > 1:
        return None, contains
    close_names = difflib.get_close_matches(service_name, [t["name"] for t in treatments], n=3, cutoff=0.5)
    matches = [t for t in treatments if t["name"] in close_names]
    if len(matches) == 1:
        return matches[0], []
    return None, matches


# --- Services ---

async def _list_services(db: AsyncSession, customer: Customer, query: str | None = None) -> dict:
    org_id, branches = await _resolve_org(db, customer)
    branch = _default_branch(branches)
    if not branch:
        return {"error": "NO_BRANCH", "message": "No active branch configured for this clinic."}

    treatments = await get_clinicmd_client().list_treatments(org_id, branch)
    if query:
        q = query.lower()
        filtered = [t for t in treatments if q in t["name"].lower() or q in (t.get("category") or "").lower()]
        if filtered:
            treatments = filtered

    return {
        "branch": {"id": branch["id"], "name": branch["name"]},
        "services": [
            {
                "id": t["id"],
                "name": t["name"],
                "category": t.get("category"),
                "duration_minutes": t.get("duration_minutes") or avail.DEFAULT_DURATION_MINUTES,
                "price_npr": t.get("price_npr"),
                "description": (t.get("description") or "")[:300],
            }
            for t in treatments
        ],
    }


# --- Availability ---

async def _next_open_slots(client, branch: dict, treatment: dict, now_npt: datetime, want: int = 3) -> list[dict]:
    duration = treatment.get("duration_minutes") or avail.DEFAULT_DURATION_MINUTES
    start = now_npt.date()
    end = start + timedelta(days=avail.MAX_DAYS_AHEAD)
    chairs = await client.list_chairs(branch["id"])
    bookings = await client.bookings_range(branch["id"], start.isoformat(), end.isoformat())

    by_date: dict[str, list[dict]] = {}
    for b in bookings:
        by_date.setdefault(str(b.get("booking_date")), []).append(b)

    results = []
    for offset in range(avail.MAX_DAYS_AHEAD + 1):
        day = start + timedelta(days=offset)
        day_str = day.isoformat()
        slots = avail.available_slots_for_date(day, duration, chairs, by_date.get(day_str, []), now_npt, limit=1)
        if slots:
            results.append({"date": day_str, "time": slots[0]})
        if len(results) >= want:
            break
    return results


async def _check_availability(db: AsyncSession, customer: Customer, service: str, date: str | None = None) -> dict:
    org_id, branches = await _resolve_org(db, customer)
    branch = _default_branch(branches)
    if not branch:
        return {"error": "NO_BRANCH", "message": "No active branch configured for this clinic."}

    client = get_clinicmd_client()
    treatments = await client.list_treatments(org_id, branch)
    treatment, ambiguous = _match_service(treatments, service)
    if treatment is None:
        if ambiguous:
            return {"ambiguous": True, "options": [{"id": t["id"], "name": t["name"]} for t in ambiguous]}
        return {"error": "SERVICE_NOT_FOUND", "message": f"Couldn't find a service matching '{service}'."}

    now_npt = datetime.now(NPT)
    service_summary = {
        "id": treatment["id"],
        "branch_id": branch["id"],
        "name": treatment["name"],
        "duration_minutes": treatment.get("duration_minutes") or avail.DEFAULT_DURATION_MINUTES,
        "price_npr": treatment.get("price_npr"),
    }

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "INVALID_DATE", "message": "Date must be in YYYY-MM-DD format."}
        chairs = await client.list_chairs(branch["id"])
        bookings = await client.bookings_range(branch["id"], date, date)
        slots = avail.available_slots_for_date(
            target_date, service_summary["duration_minutes"], chairs, bookings, now_npt, limit=8
        )
        return {"service": service_summary, "date": date, "open_times": slots}

    next_slots = await _next_open_slots(client, branch, treatment, now_npt)
    return {"service": service_summary, "next_open_slots": next_slots}


# --- Booking ---

def _pending_public_view(pending: dict) -> dict:
    return {k: v for k, v in pending.items() if k != "prepared_turn"}


async def _prepare_booking(
    db: AsyncSession,
    customer: Customer,
    session_id: str,
    current_turn: int,
    service_id: str,
    branch_id: str,
    date: str,
    time: str,
    full_name: str,
    phone: str,
    email: str | None = None,
    note: str | None = None,
) -> dict:
    if not session_id or not session_id.strip():
        return {"error": "MISSING_SESSION", "message": "A session is required to prepare a booking."}

    org_id, branches = await _resolve_org(db, customer)
    branch = next((b for b in branches if b["id"] == branch_id), None)
    if not branch:
        return {"error": "INVALID_BRANCH", "message": "That branch isn't available."}

    client = get_clinicmd_client()
    treatments = await client.list_treatments(org_id, branch)
    treatment = next((t for t in treatments if t["id"] == service_id), None)
    if not treatment:
        return {"error": "INVALID_SERVICE", "message": "That service isn't available."}

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        datetime.strptime(time, "%H:%M")
    except ValueError:
        return {"error": "INVALID_DATETIME", "message": "Date must be YYYY-MM-DD and time HH:MM."}

    phone_e164 = to_e164(phone)
    if not phone_e164:
        return {"error": "INVALID_PHONE", "message": "A valid phone number is required."}
    if not full_name or not full_name.strip():
        return {"error": "INVALID_NAME", "message": "The visitor's full name is required."}

    now_npt = datetime.now(NPT)
    duration = treatment.get("duration_minutes") or avail.DEFAULT_DURATION_MINUTES
    chairs = await client.list_chairs(branch["id"])
    bookings = await client.bookings_range(branch["id"], date, date)
    slots = avail.available_slots_for_date(target_date, duration, chairs, bookings, now_npt)

    if time not in slots:
        return {
            "error": "SLOT_TAKEN",
            "message": "That time is no longer open.",
            "alternatives": slots[:3],
        }

    pending = {
        "service_id": treatment["id"],
        "service_name": treatment["name"],
        "branch_id": branch["id"],
        "branch_name": branch["name"],
        "date": date,
        "time": time,
        "full_name": full_name.strip(),
        "phone_e164": phone_e164,
        "email": (email or "").strip() or None,
        "note": (note or "").strip(),
        "price_npr": treatment.get("price_npr"),
        "prepared_turn": current_turn,
    }
    _state(session_id)["pending"] = pending

    price = treatment.get("price_npr")
    price_str = f" Price: NPR {price}." if price is not None else ""
    summary = (
        f"{treatment['name']} on {date} at {time} for {full_name.strip()} "
        f"({phone_e164}) at {branch['name']}.{price_str}"
    )
    return {"summary": summary, "pending_booking": _pending_public_view(pending)}


async def _execute_booking(db: AsyncSession, customer: Customer, pending: dict) -> dict:
    client = get_clinicmd_client()
    org_id, branches = await _resolve_org(db, customer)
    branch = next((b for b in branches if b["id"] == pending["branch_id"]), None)
    if not branch:
        raise ClinicMdError("Branch no longer available.", code="BRANCH_NOT_FOUND")

    treatments = await client.list_treatments(org_id, branch)
    treatment = next((t for t in treatments if t["id"] == pending["service_id"]), None)
    if not treatment:
        raise ClinicMdError("Service no longer available.", code="SERVICE_NOT_FOUND")

    duration = treatment.get("duration_minutes") or avail.DEFAULT_DURATION_MINUTES
    target_date = datetime.strptime(pending["date"], "%Y-%m-%d").date()
    now_npt = datetime.now(NPT)

    chairs = await client.list_chairs(branch["id"])
    bookings = await client.bookings_range(branch["id"], pending["date"], pending["date"])
    start_minutes = avail.parse_hhmm_to_minutes(pending["time"])

    if target_date == now_npt.date() and start_minutes <= now_npt.hour * 60 + now_npt.minute:
        raise ClinicMdError("That time has already passed.", code="SLOT_TAKEN", pg_code="P0003")

    chair = avail.find_available_chair(start_minutes, duration, chairs, avail.build_occupancy(bookings))
    if not chair:
        raise ClinicMdError("Slot no longer available.", code="SLOT_TAKEN", pg_code="P0003")

    customer_id = await client.upsert_customer(
        org_id, branch["id"], pending["full_name"], pending["phone_e164"], pending.get("email"), None
    )

    booking_id = new_booking_id()
    row = {
        "id": booking_id,
        "branch_id": branch["id"],
        "chair_id": chair["id"],
        "treatment_id": treatment["id"],
        "dentist_id": None,
        "customer_id": customer_id,
        "customer_name": pending["full_name"].title(),
        "customer_email": pending.get("email"),
        "customer_phone": pending["phone_e164"],
        "date": pending["date"],
        "start_time": pending["time"],
        "base_amount": treatment.get("price_npr"),
        "discount_amount": 0,
        "special_requests": f"[Booked via website AI assistant] {pending.get('note') or ''}".strip(),
        "created_by": None,
        "treatment_name_snapshot": treatment["name"],
        "treatment_duration_snapshot": duration,
        "treatment_price_snapshot": treatment.get("price_npr"),
        "chair_name_snapshot": chair.get("name"),
    }

    await client.insert_booking(row)
    booking = await client.get_booking(booking_id)

    return {
        "booking_number": (booking or {}).get("booking_number"),
        "date": (booking or {}).get("date", pending["date"]),
        "start_time": (booking or {}).get("start_time", pending["time"]),
        "treatment_name": treatment["name"],
        "branch_name": branch["name"],
    }


def _signature(pending: dict) -> tuple:
    return (pending["service_id"], pending["date"], pending["time"])


async def _confirm_booking(db: AsyncSession, customer: Customer, session_id: str, current_turn: int) -> dict:
    if not session_id or not session_id.strip():
        return {"error": "MISSING_SESSION", "message": "A session is required to confirm a booking."}

    state = _state(session_id)
    pending = state.get("pending")

    if not pending:
        return {
            "error": "NO_PENDING_BOOKING",
            "message": "There's no booking staged yet. Please call prepare_booking first.",
        }

    if pending["prepared_turn"] == current_turn:
        return {
            "error": "NEEDS_CONFIRMATION",
            "message": "The visitor hasn't replied to the booking summary yet. Read it back and wait for their explicit yes before confirming.",
        }

    sig = _signature(pending)
    for entry in state["confirmed"]:
        if entry["signature"] == sig:
            return {"booking": entry["booking"], "already_booked": True}

    try:
        booking = await _execute_booking(db, customer, pending)
    except ClinicMdError as e:
        if e.pg_code in ("P0003", "P0005"):
            org_id, branches = await _resolve_org(db, customer)
            branch = next((b for b in branches if b["id"] == pending["branch_id"]), None)
            alternatives: list[dict] = []
            if branch:
                treatments = await get_clinicmd_client().list_treatments(org_id, branch)
                treatment = next((t for t in treatments if t["id"] == pending["service_id"]), None)
                if treatment:
                    alternatives = await _next_open_slots(get_clinicmd_client(), branch, treatment, datetime.now(NPT))
            return {
                "error": "SLOT_TAKEN",
                "message": "That slot was just taken by someone else.",
                "alternatives": alternatives,
            }
        logger.warning("[CLINIC-AGENT] booking_failed pg_code=%s", e.pg_code)
        return {
            "error": "BOOKING_FAILED",
            "message": "Something went wrong creating the booking. Please try again or call the clinic directly.",
        }

    state["confirmed"].append({"signature": sig, "booking": booking})
    # Deliberately NOT clearing pending: a duplicate confirm_booking call (LLM
    # double-call, IG-8 lesson) must still find prepared_turn + can match the
    # signature above instead of hitting the "no pending booking" guard.
    logger.info("[CLINIC-AGENT] booking_created booking_number=%s", booking.get("booking_number"))
    return {"booking": booking}
