"""
ZUNKIREE-CLINIC-AGENT-BRIEF §7:
- Chair pick + E.164 normalization.
- confirm_booking: no pending -> refuse; same-turn -> refuse; double call -> one insert.
- Error mapping P0003/P0005 -> SLOT_TAKEN with alternatives.

ClinicMdClient is mocked/monkeypatched throughout — no test hits real ClinicMD.
"""
import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.customer import Customer
from app.services.clinicmd_client import ClinicMdError
from app.services import clinic_tools


ORG_ID = "org-1"
BRANCH = {"id": "branch-1", "name": "Thimi Branch", "excluded_treatment_categories": []}
TREATMENT = {
    "id": "svc-1",
    "name": "Teeth Cleaning",
    "duration_minutes": 60,
    "price_npr": 1500,
    "category": "General",
    "description": "A routine cleaning.",
}
CHAIRS = [{"id": "chair-1", "name": "Chair 1", "capacity": 1}]


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        name="The Dental City",
        site_id="dental-city",
        api_key="test-key",
    )


@pytest.fixture(autouse=True)
def _reset_state():
    clinic_tools.reset_org_cache()
    yield
    clinic_tools.reset_org_cache()
    clinic_tools.reset_session_state("s1")


@pytest.fixture(autouse=True)
def _patch_resolve_org(monkeypatch):
    async def fake_resolve_org(db, customer):
        return ORG_ID, [BRANCH]

    monkeypatch.setattr(clinic_tools, "_resolve_org", fake_resolve_org)


class FakeClient:
    def __init__(self, treatments=None, chairs=None, bookings=None, insert_error=None):
        self.treatments = treatments if treatments is not None else [TREATMENT]
        self.chairs = chairs if chairs is not None else CHAIRS
        self.bookings = bookings if bookings is not None else []
        self.insert_error = insert_error
        self.insert_calls = 0
        self.inserted_rows = []

    async def list_treatments(self, org_id, branch=None):
        return self.treatments

    async def list_chairs(self, branch_id):
        return self.chairs

    async def bookings_range(self, branch_id, start, end):
        return self.bookings

    async def upsert_customer(self, *a, **kw):
        return "cust-1"

    async def insert_booking(self, row):
        self.insert_calls += 1
        self.inserted_rows.append(row)
        if self.insert_error:
            raise self.insert_error

    async def get_booking(self, booking_id):
        return {"booking_number": "BK-1001", "date": "2026-10-01", "start_time": "10:00"}


def _patch_client(monkeypatch, client: FakeClient):
    monkeypatch.setattr(clinic_tools, "get_clinicmd_client", lambda: client)


# --- E.164 normalization ---

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9841234567", "+9779841234567"),
        ("+977 984-123-4567", "+9779841234567"),
        ("9779841234567", "+9779841234567"),  # >10 digits already carries country code, trusted as-is
        ("+1 555-123-4567", "+15551234567"),
        ("", None),
        (None, None),
    ],
)
def test_to_e164(raw, expected):
    assert clinic_tools.to_e164(raw) == expected


def test_to_e164_bare_national_under_10_digits_gets_default_dial():
    assert clinic_tools.to_e164("9841234567") == "+9779841234567"


# --- prepare_booking + chair pick ---

@pytest.mark.asyncio
async def test_prepare_booking_picks_open_slot_and_stages_pending(monkeypatch):
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    result = await clinic_tools._prepare_booking(
        db=AsyncMock(),
        customer=customer,
        session_id="s1",
        current_turn=1,
        service="Teeth Cleaning",
        date="2026-10-01",
        time="10:00",
        full_name="jane doe",
        phone="9841234567",
    )
    assert "summary" in result
    pending = clinic_tools._state("s1")["pending"]
    assert pending["service_id"] == "svc-1"
    assert pending["phone_e164"] == "+9779841234567"
    assert pending["prepared_turn"] == 1


@pytest.mark.asyncio
async def test_prepare_booking_rejects_taken_slot(monkeypatch):
    # Chair already fully booked at 10:00
    client = FakeClient(bookings=[{"chair_id": "chair-1", "start_time": "10:00", "duration_minutes": 60}])
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    result = await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=1,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    assert result["error"] == "SLOT_TAKEN"
    assert clinic_tools._state("s1")["pending"] is None


@pytest.mark.asyncio
async def test_prepare_booking_refuses_empty_session_id(monkeypatch):
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    result = await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="", current_turn=1,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    assert result["error"] == "MISSING_SESSION"


# --- service/branch resolution (list-position id hallucination guard) ---

@pytest.mark.asyncio
async def test_prepare_booking_ignores_non_uuid_service_id_and_resolves_by_name(monkeypatch):
    """LLM sometimes echoes a list position ('1') as service_id instead of the real
    UUID — that must be ignored and the service name used instead."""
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    result = await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=1,
        service="Teeth Cleaning", service_id="1", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    assert "summary" in result
    assert clinic_tools._state("s1")["pending"]["service_id"] == "svc-1"


@pytest.mark.asyncio
async def test_prepare_booking_bad_service_name_returns_clear_error_with_options(monkeypatch):
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    result = await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=1,
        service="1", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    assert result["error"] == "SERVICE_NOT_FOUND"
    assert "1" in result["message"]
    assert result["options"] == ["Teeth Cleaning"]


@pytest.mark.asyncio
async def test_prepare_booking_ambiguous_service_name_returns_options(monkeypatch):
    treatments = [
        {**TREATMENT, "id": "svc-1", "name": "General Dentistry"},
        {**TREATMENT, "id": "svc-2", "name": "General Treatment"},
    ]
    client = FakeClient(treatments=treatments)
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    result = await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=1,
        service="General", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    assert result["error"] == "SERVICE_AMBIGUOUS"
    assert {o["name"] for o in result["options"]} == {"General Dentistry", "General Treatment"}
    assert clinic_tools._state("s1")["pending"] is None


@pytest.mark.asyncio
async def test_prepare_booking_defaults_to_single_branch_without_branch_arg(monkeypatch):
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    result = await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=1,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    assert "summary" in result
    assert clinic_tools._state("s1")["pending"]["branch_id"] == "branch-1"


@pytest.mark.asyncio
async def test_prepare_booking_multi_branch_without_branch_arg_asks_which(monkeypatch):
    branches = [BRANCH, {"id": "branch-2", "name": "Lalitpur Branch", "excluded_treatment_categories": []}]

    async def fake_resolve_org(db, customer):
        return ORG_ID, branches

    monkeypatch.setattr(clinic_tools, "_resolve_org", fake_resolve_org)
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    result = await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=1,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    assert result["error"] == "BRANCH_REQUIRED"
    assert set(result["options"]) == {"Thimi Branch", "Lalitpur Branch"}


# --- confirm_booking guards ---

@pytest.mark.asyncio
async def test_confirm_booking_refuses_empty_session_id(monkeypatch):
    customer = _make_customer()
    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "", current_turn=1)
    assert result["error"] == "MISSING_SESSION"


@pytest.mark.asyncio
async def test_confirm_booking_refuses_when_no_pending(monkeypatch):
    customer = _make_customer()
    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=1)
    assert result["error"] == "NO_PENDING_BOOKING"


@pytest.mark.asyncio
async def test_confirm_booking_refuses_same_turn(monkeypatch):
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=2,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=2)
    assert result["error"] == "NEEDS_CONFIRMATION"
    assert client.insert_calls == 0


@pytest.mark.asyncio
async def test_repeat_prepare_same_slot_preserves_original_prepared_turn(monkeypatch):
    """CLINIC-BOOKING-FLOW-VOICE-BRIEF D2: the live session showed the LLM
    re-running prepare_booking for the SAME slot immediately before
    confirm_booking, on the turn the visitor said yes. If that re-prepare
    pushed prepared_turn forward, confirm_booking's same-turn guard would
    wrongly refuse a genuine confirmation forever."""
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=5,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    # Visitor says yes on turn 6; LLM redundantly re-prepares the same slot
    # before confirming, both on turn 6.
    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=6,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    assert clinic_tools._state("s1")["pending"]["prepared_turn"] == 5

    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=6)
    assert "booking" in result
    assert client.insert_calls == 1


@pytest.mark.asyncio
async def test_repeat_prepare_same_slot_but_changed_phone_resets_prepared_turn(monkeypatch):
    """PR #64 review MUST 1: a re-prepare that keeps the same slot but
    changes a read-back field (phone — the most error-prone field on a
    voice call) must NOT preserve prepared_turn. The read-back is the only
    defence against booking a number the visitor never confirmed hearing,
    so any change to it must force a fresh confirmation."""
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=5,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    # Same slot, but a different phone number (misheard STT / visitor
    # correction) on the turn the visitor supposedly confirmed.
    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=6,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234568",
    )
    assert clinic_tools._state("s1")["pending"]["prepared_turn"] == 6

    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=6)
    assert result["error"] == "NEEDS_CONFIRMATION"
    assert client.insert_calls == 0


@pytest.mark.asyncio
async def test_repeat_prepare_different_slot_resets_prepared_turn(monkeypatch):
    """A genuinely NEW slot (not a re-prepare of the same one) must still
    reset prepared_turn to the current turn — the same-turn confirmation
    guard should still apply to an actually-new booking."""
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=5,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=6,
        service="Teeth Cleaning", date="2026-10-02", time="11:00",
        full_name="Jane", phone="9841234567",
    )
    assert clinic_tools._state("s1")["pending"]["prepared_turn"] == 6

    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=6)
    assert result["error"] == "NEEDS_CONFIRMATION"
    assert client.insert_calls == 0


@pytest.mark.asyncio
async def test_confirm_booking_succeeds_on_later_turn_and_is_idempotent(monkeypatch):
    client = FakeClient()
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=3,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )

    first = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=4)
    assert "booking" in first
    assert client.insert_calls == 1

    # Double call (LLM re-invokes confirm_booking in the same or later turn):
    # must NOT insert again, must return the same booking.
    second = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=4)
    assert second["booking"] == first["booking"]
    assert second.get("already_booked") is True
    assert client.insert_calls == 1


# --- Error mapping ---

@pytest.mark.asyncio
async def test_confirm_booking_maps_p0003_to_slot_taken_with_alternatives(monkeypatch):
    client = FakeClient(insert_error=ClinicMdError("chair full", pg_code="P0003"))
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=5,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=6)
    assert result["error"] == "SLOT_TAKEN"
    assert "alternatives" in result


@pytest.mark.asyncio
async def test_confirm_booking_maps_p0005_to_slot_taken(monkeypatch):
    client = FakeClient(insert_error=ClinicMdError("branch capacity", pg_code="P0005"))
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=7,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=8)
    assert result["error"] == "SLOT_TAKEN"


@pytest.mark.asyncio
async def test_confirm_booking_maps_other_pg_error_to_booking_failed(monkeypatch):
    client = FakeClient(insert_error=ClinicMdError("boom", pg_code="23505"))
    _patch_client(monkeypatch, client)
    customer = _make_customer()

    await clinic_tools._prepare_booking(
        db=AsyncMock(), customer=customer, session_id="s1", current_turn=9,
        service="Teeth Cleaning", date="2026-10-01", time="10:00",
        full_name="Jane", phone="9841234567",
    )
    result = await clinic_tools._confirm_booking(AsyncMock(), customer, "s1", current_turn=10)
    assert result["error"] == "BOOKING_FAILED"


@pytest.mark.asyncio
async def test_prepare_after_unmatched_service_records_substitution(monkeypatch):
    _patch_client(monkeypatch, FakeClient())
    kw = dict(db=AsyncMock(), customer=_make_customer(), session_id="s1", date="2026-10-01",
              time="10:00", full_name="Jane", phone="9841234567")
    bad = await clinic_tools._prepare_booking(current_turn=1, service="root canal xyz", **kw)
    assert bad["error"] == "SERVICE_NOT_FOUND"
    ok = await clinic_tools._prepare_booking(current_turn=1, service="Teeth Cleaning", **kw)
    assert ok["pending_booking"]["substituted_for"] == "root canal xyz"
    # same-slot re-prepare keeps it; a clean prepare in a fresh session has none
    again = await clinic_tools._prepare_booking(current_turn=2, service="Teeth Cleaning", **kw)
    assert again["pending_booking"]["substituted_for"] == "root canal xyz"
    clean = await clinic_tools._prepare_booking(current_turn=1, **{**kw, "session_id": "s2"}, service="Teeth Cleaning")
    assert clean["pending_booking"]["substituted_for"] is None
