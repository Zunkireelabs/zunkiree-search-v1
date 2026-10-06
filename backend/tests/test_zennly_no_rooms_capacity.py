"""
SBAL-Z1 follow-up: SBAL (industries.enable_rooms = false — a salon with no
fixed stations) has zero rows in `rooms`, so the room-capacity path would
always report zero availability. Capacity instead comes from active
therapist headcount by gender, ported EXACTLY from book-spa stage's
customer-booking-flow/utils/availability.js (buildOccupancy's byGender
branch) + DateTimeSelection.jsx's computedDays memo (lines 118-140, sha
a12f17c) — see clinic_availability.py's own module docstring on that
section and zennly_client.list_therapists.

insert_booking for these tenants sends exactly what Zennly's own online
flow sends: room_id=None (no room was ever selected), therapist_id=None
(the public flow never assigns one — BookingConfirmation.jsx never passes
therapistId to createBooking), created_by=None (the online-booking marker,
unchanged from the room-based path). The real race-safety guard is
Zennly's own DB trigger (check_branch_online_capacity, migration-138,
raises P0005 when branches.online_booking_capacity is configured and
exceeded) — already mapped to SLOT_TAKEN by the existing P0003/P0005
handling in _write_and_record; this file never needs to re-implement that
mapping, only exercise it on this path.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.customer import Customer
from app.services import clinic_availability as avail
from app.services import clinic_tools
from app.services.clinicmd_client import ClinicMdError
from app.services.zennly_client import ZennlyError


def _customer(site_id="sbal"):
    return Customer(id=uuid.uuid4(), site_id=site_id, name="SBAL", website_type="clinic")


# ---------------------------------------------------------------------------
# Pure headcount-capacity functions — ported from availability.js /
# DateTimeSelection.jsx, tested against the exact rules those files encode.
# ---------------------------------------------------------------------------


def test_build_gender_occupancy_buckets_by_30min_grid_and_ignores_ungendered():
    bookings = [
        {"start_time": "10:05", "duration_minutes": 60, "therapist_gender": "Female"},
        {"start_time": "10:30", "duration_minutes": 30, "therapist_gender": None},  # no therapist assigned
    ]
    occ = avail.build_gender_occupancy(bookings)
    # 10:05 + 60min ends at 11:05; grid-floored start is 10:00, so the
    # occupied buckets are 10:00, 10:30, 11:00 (11:00 < 11:05, still inside).
    assert occ[600] == {"male": 0, "female": 1}
    assert occ[630] == {"male": 0, "female": 1}
    assert occ[660] == {"male": 0, "female": 1}
    assert 690 not in occ
    # the ungendered (therapist_id was never assigned) booking contributes nothing
    assert occ[630]["male"] == 0


def test_is_slot_available_by_headcount_no_preference_is_or_not_sum():
    """genderOk with no preference: EITHER gender having a free therapist is
    enough — DateTimeSelection.jsx:137-140. Must NOT sum male+female."""
    counts = {"male": 0, "female": 1}
    occupancy = {}  # nothing booked yet
    assert avail.is_slot_available_by_headcount(600, 60, counts, occupancy, gender=None) is True
    # Exhaust the one female therapist for this slot.
    occupancy = avail.build_gender_occupancy(
        [{"start_time": "10:00", "duration_minutes": 60, "therapist_gender": "Female"}]
    )
    assert avail.is_slot_available_by_headcount(600, 60, counts, occupancy, gender=None) is False


def test_is_slot_available_by_headcount_respects_explicit_gender_preference():
    counts = {"male": 1, "female": 1}
    occupancy = avail.build_gender_occupancy(
        [{"start_time": "10:00", "duration_minutes": 60, "therapist_gender": "Female"}]
    )
    # female therapist is booked, but male is free
    assert avail.is_slot_available_by_headcount(600, 60, counts, occupancy, gender="female") is False
    assert avail.is_slot_available_by_headcount(600, 60, counts, occupancy, gender="male") is True
    # no preference: male still free, so overall available
    assert avail.is_slot_available_by_headcount(600, 60, counts, occupancy, gender=None) is True


def test_is_slot_available_by_headcount_zero_count_gender_never_available():
    """A gender with zero active therapists must never show available —
    matches `therapistCounts.male - booked.male <= 0` with booked.male
    always 0 too (DateTimeSelection.jsx:133)."""
    counts = {"male": 0, "female": 6}
    assert avail.is_slot_available_by_headcount(600, 60, counts, {}, gender="male") is False


def test_available_slots_for_date_by_headcount_applies_past_cutoff_today():
    import datetime as dt
    now_npt = dt.datetime(2026, 10, 10, 11, 0)
    slots = avail.available_slots_for_date_by_headcount(
        dt.date(2026, 10, 10), 60, {"male": 0, "female": 1}, [], now_npt,
    )
    assert "10:30" not in slots  # already past
    assert "11:30" in slots


def test_therapist_counts_matches_jsx_query_shape():
    therapists = [
        {"id": "t1", "name": "Jayanti", "gender": "Female", "is_active": True},
        {"id": "t2", "name": "Sami", "gender": "Female"},
        {"id": "t3", "name": "X", "gender": None},  # ungendered — counted nowhere, same as the real page
    ]
    assert clinic_tools._therapist_counts(therapists) == {"male": 0, "female": 2}


# ---------------------------------------------------------------------------
# clinic_tools integration: _check_availability / _execute_booking on the
# enable_rooms=false path, through a fake ZennlyClient.
# ---------------------------------------------------------------------------


class FakeNoRoomsClient:
    """Same method surface as ZennlyClient. list_chairs is deliberately
    absent/would-error if called — enable_rooms=false must never call it."""

    def __init__(self, treatments, therapists, bookings=None):
        self.treatments = treatments
        self.therapists = therapists
        self.bookings = bookings or []
        self.inserted_row = None

    async def list_treatments(self, org_id, branch=None):
        return self.treatments

    async def list_therapists(self, branch_id):
        return self.therapists

    async def bookings_range(self, branch_id, start_date, end_date):
        return self.bookings

    async def upsert_customer(self, *a, **kw):
        return "cust-1"

    async def insert_booking(self, row):
        self.inserted_row = row

    async def get_booking(self, booking_id):
        return {"booking_number": "BK-SBAL-1", "date": "2026-10-10", "start_time": "10:00"}


TREATMENT = {"id": "svc-1", "name": "Brow Lamination", "duration_minutes": 60, "price_npr": 3499}
BRANCH = {"id": "b1", "name": "Main Branch"}


def _seed_org_cache(site_id="sbal"):
    clinic_tools._cache_set(clinic_tools._ORG_CACHE, site_id, {
        "org_id": "org-sbal", "branches": [BRANCH], "backend_type": "zennly",
        "vocab": {"staff_term": "staff"}, "enable_rooms": False,
    })


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    clinic_tools.reset_org_cache()
    yield
    clinic_tools.reset_org_cache()


@pytest.mark.asyncio
async def test_check_availability_uses_headcount_not_rooms(monkeypatch):
    _seed_org_cache()
    therapists = [{"id": "t1", "gender": "Female", "is_active": True}]
    fake = FakeNoRoomsClient([TREATMENT], therapists, bookings=[])
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)

    result = await clinic_tools._check_availability(
        AsyncMock(), _customer(), "Brow Lamination", date="2026-10-12",
    )
    assert "open_times" in result
    assert len(result["open_times"]) > 0  # one female therapist, no bookings -> available


@pytest.mark.asyncio
async def test_check_availability_no_rooms_never_calls_list_chairs(monkeypatch):
    """FakeNoRoomsClient has no list_chairs method at all — if the
    enable_rooms=false branch ever called it, this would AttributeError."""
    _seed_org_cache()
    fake = FakeNoRoomsClient([TREATMENT], [{"id": "t1", "gender": "Female", "is_active": True}])
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)

    result = await clinic_tools._check_availability(
        AsyncMock(), _customer(), "Brow Lamination", date="2026-10-12",
    )
    assert "error" not in result


@pytest.mark.asyncio
async def test_execute_booking_no_rooms_sends_room_id_and_therapist_id_null(monkeypatch):
    _seed_org_cache()
    fake = FakeNoRoomsClient([TREATMENT], [{"id": "t1", "gender": "Female", "is_active": True}], bookings=[])
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)
    monkeypatch.setattr(clinic_tools, "new_booking_id", lambda: "req-fixed")

    pending = {
        "service_id": "svc-1", "branch_id": "b1", "date": "2026-10-12", "time": "11:00",
        "full_name": "test user", "phone_e164": "+9779841230000", "email": None, "note": None,
        "gender_preference": None,
    }
    result = await clinic_tools._execute_booking(AsyncMock(), _customer(), pending)

    assert fake.inserted_row["room_id"] is None
    assert fake.inserted_row["therapist_id"] is None
    assert fake.inserted_row["created_by"] is None
    assert fake.inserted_row["room_name_snapshot"] is None
    assert result["booking_number"] == "BK-SBAL-1"


@pytest.mark.asyncio
async def test_execute_booking_no_rooms_rejects_when_gender_capacity_exhausted(monkeypatch):
    """The 'last free therapist' case: one active female therapist, one
    existing booking already occupying 11:00-12:00 with a female therapist
    -> the slot must be rejected locally (SLOT_TAKEN) before ever reaching
    insert_booking."""
    _seed_org_cache()
    existing_booking = {"start_time": "11:00", "duration_minutes": 60, "therapist_gender": "Female"}
    fake = FakeNoRoomsClient(
        [TREATMENT], [{"id": "t1", "gender": "Female", "is_active": True}], bookings=[existing_booking],
    )
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)

    pending = {
        "service_id": "svc-1", "branch_id": "b1", "date": "2026-10-12", "time": "11:00",
        "full_name": "test user", "phone_e164": "+9779841230000", "email": None, "note": None,
        "gender_preference": None,
    }
    with pytest.raises(ClinicMdError) as exc_info:
        await clinic_tools._execute_booking(AsyncMock(), _customer(), pending)
    assert exc_info.value.pg_code == "P0003"
    assert fake.inserted_row is None  # never reached the write


# ---------------------------------------------------------------------------
# "Two bookings for the last free therapist -> one SLOT_TAKEN": the real
# race-safety mechanism is Zennly's own DB trigger (migration-138), which
# raises P0005 — already mapped to SLOT_TAKEN by _write_and_record for every
# backend. This exercises that exact mapping on the no-rooms/zennly path,
# with alternatives sourced from the headcount model (not rooms).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_booking_for_last_therapist_second_caller_gets_slot_taken(monkeypatch):
    _seed_org_cache()

    class RaceClient(FakeNoRoomsClient):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.insert_attempts = 0

        async def insert_booking(self, row):
            self.insert_attempts += 1
            if self.insert_attempts >= 2:
                # Zennly's check_branch_online_capacity trigger (migration-138)
                raise ZennlyError(
                    "BRANCH_ONLINE_CAPACITY: No therapists available at this branch for the selected time.",
                    pg_code="P0005",
                )
            self.inserted_row = row

    fake = RaceClient([TREATMENT], [{"id": "t1", "gender": "Female", "is_active": True}], bookings=[])
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)
    monkeypatch.setattr(clinic_tools, "new_booking_id", lambda: "req-fixed")

    pending = {
        "service_id": "svc-1", "branch_id": "b1", "date": "2026-10-12", "time": "11:00",
        "full_name": "test user", "phone_e164": "+9779841230000", "email": None, "note": None,
        "gender_preference": None, "prepared_turn": 1,
    }
    state = {"confirmed": []}

    first = await clinic_tools._write_and_record(AsyncMock(), _customer(), state, dict(pending))
    assert first["booking"]["booking_number"] == "BK-SBAL-1"

    # Same signature, so a repeat is idempotent (this IS the double-call
    # guard) — use a second visitor's distinct pending (different time) to
    # actually reach a fresh insert_booking attempt for "someone else".
    pending_2 = {**pending, "time": "11:00", "service_id": "svc-1"}
    # Force a genuinely new signature by varying the date, so _write_and_record
    # doesn't short-circuit on the already-confirmed signature from `first`.
    pending_2["date"] = "2026-10-13"
    second = await clinic_tools._write_and_record(AsyncMock(), _customer(), state, pending_2)

    assert second["error"] == "SLOT_TAKEN"
    assert second["message"] == "That slot was just taken by someone else."
