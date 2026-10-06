"""
SBAL-Z1: the clinic agent's booking backend is now per-tenant DATA
(tenant_backend_credentials.backend_type), not hardcoded to ClinicMD. These
tests cover the routing/dispatch layer in clinic_tools.py — zennly_client.py
itself is unit-tested in test_zennly_client.py, clinicmd_client.py in
test_clinicmd_client.py (unchanged).

Key regression guard: a "clinicmd" tenant must still produce the EXACT same
booking row shape as before this change (see
test_execute_booking_clinicmd_row_is_unchanged).
"""
import uuid
from types import SimpleNamespace

import pytest

from app.models.customer import Customer
from app.services import clinic_tools
from app.services.clinicmd_client import ClinicMdError
from app.services.zennly_client import ZennlyError


def _customer(site_id="t1"):
    return Customer(id=uuid.uuid4(), site_id=site_id, name="T", website_type="clinic")


class FakeSession:
    """Returns a single TenantBackendCredentials-shaped row."""

    def __init__(self, backend_type: str, remote_site_id: str = "slug-1"):
        self.row = SimpleNamespace(backend_type=backend_type, remote_site_id=remote_site_id, is_active=True)

    async def execute(self, *_a, **_kw):
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)

    async def commit(self):
        pass


class FakeClient:
    """Minimal booking-backend client — same method surface as
    ClinicMdClient/ZennlyClient. Records calls for assertions."""

    def __init__(self, org, branches, treatments, chairs, bookings=None):
        self._org = org
        self._branches = branches
        self._treatments = treatments
        self._chairs = chairs
        self._bookings = bookings or []
        self.inserted_row = None
        self.customer_id = "cust-1"

    async def get_org(self, slug):
        return self._org

    async def list_branches(self, org_id):
        return self._branches

    async def list_treatments(self, org_id, branch=None):
        return self._treatments

    async def list_chairs(self, branch_id):
        return self._chairs

    async def bookings_range(self, branch_id, start_date, end_date):
        return self._bookings

    async def upsert_customer(self, *a, **kw):
        return self.customer_id

    async def insert_booking(self, row):
        self.inserted_row = row

    async def get_booking(self, booking_id):
        return {"booking_number": "BK-1", "date": "2026-10-10", "start_time": "10:00"}


@pytest.fixture(autouse=True)
def _reset_caches():
    clinic_tools.reset_org_cache()
    yield
    clinic_tools.reset_org_cache()


@pytest.mark.asyncio
async def test_resolve_org_caches_zennly_backend_type_and_vocab(monkeypatch):
    db = FakeSession(backend_type="zennly", remote_site_id="sbal")
    customer = _customer("sbal")

    org = {"id": "org-1", "staff_label_plural": "Lash Artists"}
    fake = FakeClient(org, [{"id": "b1", "name": "Main"}], [], [])
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)

    org_id, branches, backend_type = await clinic_tools._resolve_org(db, customer)

    assert org_id == "org-1"
    assert backend_type == "zennly"
    assert clinic_tools._cached_backend_type("sbal") == "zennly"
    assert clinic_tools.get_vocab_for_customer("sbal") == {"staff_term": "lash artists"}
    assert clinic_tools.get_client_for_customer(customer) is fake


@pytest.mark.asyncio
async def test_resolve_org_defaults_vocab_for_clinicmd(monkeypatch):
    db = FakeSession(backend_type="clinicmd", remote_site_id="dental-city")
    customer = _customer("dental-city")

    org = {"id": "org-2"}  # no staff_label_plural — ClinicMD never sets one
    fake = FakeClient(org, [{"id": "b1", "name": "Main"}], [], [])
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)

    await clinic_tools._resolve_org(db, customer)

    assert clinic_tools._cached_backend_type("dental-city") == "clinicmd"
    assert clinic_tools.get_vocab_for_customer("dental-city") == {"staff_term": "doctors"}


def test_get_vocab_for_customer_falls_back_when_uncached():
    assert clinic_tools.get_vocab_for_customer("never-resolved") == {"staff_term": "doctors"}


def test_build_clinic_tools_substitutes_staff_term():
    tools = clinic_tools.build_clinic_tools({"staff_term": "lash artists"})
    search_tool = next(t for t in tools if t["function"]["name"] == "search_knowledge")
    assert "lash artists" in search_tool["function"]["description"]
    assert "doctors" not in search_tool["function"]["description"]
    # The static default list is untouched (no vocab substitution mutates it).
    default_search_tool = next(t for t in clinic_tools.CLINIC_TOOLS if t["function"]["name"] == "search_knowledge")
    assert "{staff_term}" in default_search_tool["function"]["description"]


@pytest.mark.asyncio
async def test_execute_booking_clinicmd_row_is_unchanged(monkeypatch):
    """Regression: backend_type="clinicmd" must still build the EXACT same
    insert_booking row this code produced before per-tenant backend routing."""
    clinic_tools._cache_set(clinic_tools._ORG_CACHE, "dental-city", {
        "org_id": "org-1", "branches": [{"id": "b1", "name": "Main"}],
        "backend_type": "clinicmd", "vocab": {"staff_term": "doctors"},
    })
    treatment = {"id": "svc-1", "name": "General Dentistry", "duration_minutes": 60, "price_npr": 1500}
    chair = {"id": "chair-1", "name": "Chair 1", "capacity": 1}
    fake = FakeClient({"id": "org-1"}, [{"id": "b1", "name": "Main"}], [treatment], [chair], bookings=[])
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)
    monkeypatch.setattr(clinic_tools, "new_booking_id", lambda: "booking-uuid-fixed")

    customer = _customer("dental-city")
    db = FakeSession(backend_type="clinicmd")
    pending = {
        "service_id": "svc-1", "branch_id": "b1", "date": "2026-10-10", "time": "10:00",
        "full_name": "jane doe", "phone_e164": "+9779841234567", "email": None, "note": None,
    }

    result = await clinic_tools._execute_booking(db, customer, pending)

    assert fake.inserted_row == {
        "id": "booking-uuid-fixed",
        "branch_id": "b1",
        "chair_id": "chair-1",
        "treatment_id": "svc-1",
        "dentist_id": None,
        "customer_id": "cust-1",
        "customer_name": "Jane Doe",
        "customer_email": None,
        "customer_phone": "+9779841234567",
        "date": "2026-10-10",
        "start_time": "10:00",
        "base_amount": 1500,
        "discount_amount": 0,
        "special_requests": "[Booked via website AI assistant]",
        "created_by": None,
        "treatment_name_snapshot": "General Dentistry",
        "treatment_duration_snapshot": 60,
        "treatment_price_snapshot": 1500,
        "chair_name_snapshot": "Chair 1",
    }
    assert result["booking_number"] == "BK-1"


@pytest.mark.asyncio
async def test_execute_booking_zennly_row_shape(monkeypatch):
    clinic_tools._cache_set(clinic_tools._ORG_CACHE, "sbal", {
        "org_id": "org-1", "branches": [{"id": "b1", "name": "Main"}],
        "backend_type": "zennly", "vocab": {"staff_term": "lash artists"},
    })
    treatment = {"id": "svc-1", "name": "Eyebrow Threading", "duration_minutes": 20, "price_npr": 400}
    room = {"id": "room-1", "name": "Room A", "capacity": 2}
    fake = FakeClient({"id": "org-1"}, [{"id": "b1", "name": "Main"}], [treatment], [room], bookings=[])
    monkeypatch.setattr(clinic_tools, "_client_for_backend", lambda bt: fake)
    monkeypatch.setattr(clinic_tools, "new_booking_id", lambda: "req-fixed")

    customer = _customer("sbal")
    db = FakeSession(backend_type="zennly")
    pending = {
        "service_id": "svc-1", "branch_id": "b1", "date": "2026-10-10", "time": "11:00",
        "full_name": "sami rai", "phone_e164": "+9779841230000", "email": None, "note": "via demo",
    }

    result = await clinic_tools._execute_booking(db, customer, pending)

    assert fake.inserted_row == {
        "client_request_id": "req-fixed",
        "branch_id": "b1",
        "room_id": "room-1",
        "service_id": "svc-1",
        "therapist_id": None,
        "customer_id": "cust-1",
        "customer_name": "Sami Rai",
        "customer_email": None,
        "customer_phone": "+9779841230000",
        "date": "2026-10-10",
        "start_time": "11:00",
        "base_amount": 400,
        "discount_amount": 0,
        "special_requests": "[Booked via website AI assistant] via demo",
        "created_by": None,
        "service_name_snapshot": "Eyebrow Threading",
        "service_duration_snapshot": 20,
        "service_price_snapshot": 400,
        "room_name_snapshot": "Room A",
    }
    # created_by is the ONLY marker Zennly's own dashboard needs to show this
    # as an "Online booking" (isOnline: !b.created_by) — assert explicitly.
    assert fake.inserted_row["created_by"] is None
    assert result["booking_number"] == "BK-1"


@pytest.mark.asyncio
async def test_execute_clinic_tool_catches_zennly_errors_like_clinicmd(monkeypatch):
    async def _boom(*a, **kw):
        raise ZennlyError("boom", pg_code="P0003")

    monkeypatch.setattr(clinic_tools, "_check_availability", _boom)
    customer = _customer("sbal")
    result = await clinic_tools.execute_clinic_tool(
        tool_name="check_availability", tool_args={"service": "Threading"},
        db=FakeSession("zennly"), customer=customer, config=None,
        site_id="sbal", session_id="s1", current_turn=1,
    )
    assert result == {"error": "CLINICMD_ERROR", "message": "I couldn't reach the booking system just now. Please try again shortly."}
