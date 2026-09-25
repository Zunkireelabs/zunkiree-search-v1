"""
PARALLEL-TOOL-SESSION-BRIEF (brain folder): the all-check_availability fan-out
in clinic_agent runs N tasks on ONE request-scoped AsyncSession. On a cold or
expired _ORG_CACHE, every task went to _resolve_org's db.execute at once and
SQLAlchemy raised "This session is provisioning a new connection; concurrent
operations are not permitted" (stage 2026-09-25 09:05:47 UTC).

The fake session below reproduces that guard: any execute()/commit() that
starts while another is still in flight raises the same InvalidRequestError.
"""
import asyncio
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import InvalidRequestError

from app.models.customer import Customer
from app.services import clinic_tools
from app.services.clinicmd_client import ClinicMdError

ORG = {"id": "org-1"}
BRANCH = {"id": "branch-1", "name": "Thimi Branch", "excluded_treatment_categories": []}
TREATMENTS = [
    {"id": f"svc-{i}", "name": n, "duration_minutes": 60, "price_npr": 1500}
    for i, n in enumerate(["Teeth Cleaning", "General Dentistry", "Dental Checkup"], 1)
]
CHAIRS = [{"id": "chair-1", "name": "Chair 1", "capacity": 1}]
SERVICES = [t["name"] for t in TREATMENTS]


class SingleOpSession:
    """Stand-in for AsyncSession: one operation at a time, like the real one."""

    def __init__(self, row="ok"):
        self.busy = False
        self.execute_calls = 0
        self.row = SimpleNamespace(remote_site_id="dental-city") if row == "ok" else None

    async def _op(self):
        if self.busy:
            raise InvalidRequestError(
                "This session is provisioning a new connection; concurrent operations are not permitted"
            )
        self.busy = True
        try:
            await asyncio.sleep(0.01)  # yield so a concurrent caller can collide
        finally:
            self.busy = False

    async def execute(self, *_a, **_kw):
        self.execute_calls += 1
        await self._op()
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)

    async def commit(self):
        await self._op()


class FakeClient:
    def __init__(self):
        self.get_org_calls = 0

    async def get_org(self, remote_site_id):
        self.get_org_calls += 1
        await asyncio.sleep(0.01)
        return ORG

    async def list_branches(self, org_id):
        return [BRANCH]

    async def list_treatments(self, org_id, branch=None):
        return TREATMENTS

    async def list_chairs(self, branch_id):
        return CHAIRS

    async def bookings_range(self, branch_id, start, end):
        return []


def _customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000dd"),
        name="Dental City", site_id="dental-city", api_key="k", website_type="clinic",
    )


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    clinic_tools.reset_org_cache()
    client = FakeClient()
    monkeypatch.setattr(clinic_tools, "get_clinicmd_client", lambda: client)
    yield client
    clinic_tools.reset_org_cache()


async def _three_parallel(db):
    customer = _customer()
    return await asyncio.gather(*(
        clinic_tools.execute_clinic_tool(
            tool_name="check_availability",
            tool_args={"service": svc, "date": "2026-09-26"},
            db=db, customer=customer, config=None, site_id="dental-city",
            session_id="s1", current_turn=1,
        )
        for svc in SERVICES
    ))


def _assert_all_ok(results):
    for r in results:
        assert "error" not in r, r
        assert r["service"]["branch_id"] == "branch-1"


@pytest.mark.asyncio
async def test_cold_cache_three_parallel_check_availability(_reset):
    """Cold cache (fresh process): 3 parallel calls share one session safely,
    and the org is resolved once, not three times."""
    db = SingleOpSession()
    results = await _three_parallel(db)
    _assert_all_ok(results)
    assert db.execute_calls == 1
    assert _reset.get_org_calls == 1


@pytest.mark.asyncio
async def test_expired_cache_three_parallel_check_availability(_reset):
    """The stage incident: a cache entry past its TTL (#92) sends every
    parallel task to the shared session."""
    clinic_tools._cache_set(clinic_tools._ORG_CACHE, "dental-city", {"org_id": "org-1", "branches": [BRANCH]})
    value, _ = clinic_tools._ORG_CACHE["dental-city"]
    clinic_tools._ORG_CACHE["dental-city"] = (
        value, clinic_tools._time.monotonic() - clinic_tools._ORG_CACHE_TTL_SECONDS - 1,
    )
    db = SingleOpSession()
    results = await _three_parallel(db)
    _assert_all_ok(results)
    assert db.execute_calls == 1


@pytest.mark.asyncio
async def test_warm_cache_three_parallel_never_touches_session(_reset):
    clinic_tools._cache_set(clinic_tools._ORG_CACHE, "dental-city", {"org_id": "org-1", "branches": [BRANCH]})
    db = SingleOpSession()
    results = await _three_parallel(db)
    _assert_all_ok(results)
    assert db.execute_calls == 0


@pytest.mark.asyncio
async def test_unconfigured_tenant_fails_cleanly_not_with_session_error(_reset):
    """If the credential lookup fails, the waiting tasks retry one at a time
    and each reports NOT_CONFIGURED; none of them collides on the session."""
    db = SingleOpSession(row=None)
    results = await _three_parallel(db)
    for r in results:
        assert "InvalidRequestError" not in str(r)
        assert "concurrent operations" not in str(r)
    assert db.execute_calls == 3  # serialised, one lookup each
