"""
ClinicMdClient mocked with httpx.MockTransport — no test hits real ClinicMD.
Patches httpx.AsyncClient itself so the client's real _get/_post_rpc/insert_booking
code runs unmodified against the fake transport.
"""
import json
from functools import partial

import httpx
import pytest

from app.services.clinicmd_client import ClinicMdClient, ClinicMdError


def _install_handler(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.fixture
def client():
    return ClinicMdClient(base_url="https://fake.supabase.co", anon_key="anon-test-key")


@pytest.mark.asyncio
async def test_get_org_sends_apikey_and_bearer_and_parses_response(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"id": "org-1", "name": "Dental City", "slug": "dental-city"}])

    _install_handler(monkeypatch, handler)
    org = await client.get_org("dental-city")

    assert org == {"id": "org-1", "name": "Dental City", "slug": "dental-city"}
    assert seen["headers"]["apikey"] == "anon-test-key"
    assert seen["headers"]["authorization"] == "Bearer anon-test-key"
    assert "slug=eq.dental-city" in seen["url"]


@pytest.mark.asyncio
async def test_get_org_returns_none_when_empty(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    _install_handler(monkeypatch, handler)
    assert await client.get_org("nope") is None


@pytest.mark.asyncio
async def test_bookings_range_posts_rpc_with_expected_payload(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json=[{"booking_date": "2026-10-01", "start_time": "10:00:00", "duration_minutes": 30, "chair_id": "c1"}],
        )

    _install_handler(monkeypatch, handler)
    rows = await client.bookings_range("branch-1", "2026-10-01", "2026-10-01")

    assert seen["path"] == "/rest/v1/rpc/public_check_branch_bookings_range"
    assert seen["body"] == {"p_branch_id": "branch-1", "p_start_date": "2026-10-01", "p_end_date": "2026-10-01"}
    assert rows[0]["chair_id"] == "c1"


@pytest.mark.asyncio
async def test_raise_for_status_extracts_postgres_error_code(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"code": "P0003", "message": "chair full"})

    _install_handler(monkeypatch, handler)
    with pytest.raises(ClinicMdError) as exc_info:
        await client.bookings_range("branch-1", "2026-10-01", "2026-10-01")
    assert exc_info.value.pg_code == "P0003"


@pytest.mark.asyncio
async def test_insert_booking_sends_return_minimal_and_client_side_id(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["prefer"] = request.headers.get("prefer")
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        return httpx.Response(201)

    _install_handler(monkeypatch, handler)
    row = {"id": "booking-uuid-1", "branch_id": "b1", "date": "2026-10-01", "start_time": "10:00"}
    await client.insert_booking(row)

    assert seen["path"] == "/rest/v1/bookings"
    assert seen["prefer"] == "return=minimal"
    assert seen["body"]["id"] == "booking-uuid-1"


@pytest.mark.asyncio
async def test_upsert_customer_failure_is_non_blocking(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": "23505", "message": "conflict"})

    _install_handler(monkeypatch, handler)
    result = await client.upsert_customer("org-1", "branch-1", "Jane Doe", "+9779841234567", None, None)
    assert result is None


def test_get_clinicmd_client_raises_when_not_configured(monkeypatch):
    from app.services import clinicmd_client as mod

    monkeypatch.setattr(mod, "_clinicmd_client", None)

    class FakeSettings:
        clinicmd_supabase_url = None
        clinicmd_supabase_anon_key = None

    monkeypatch.setattr(mod, "get_settings", lambda: FakeSettings())

    with pytest.raises(mod.ClinicMdNotConfigured):
        mod.get_clinicmd_client()


@pytest.mark.asyncio
async def test_every_call_logs_org_id(monkeypatch, client, caplog):
    from app.services.clinicmd_client import current_org_id

    _install_handler(monkeypatch, lambda request: httpx.Response(200, json=[]))
    token = current_org_id.set("org-ctx")
    try:
        with caplog.at_level("INFO", logger="zunkiree.clinicmd_client"):
            await client.list_treatments("org-explicit")  # explicit org param wins
            await client.list_chairs("branch-1")  # falls back to task context org
            await client.bookings_range("branch-1", "2026-10-01", "2026-10-01")
    finally:
        current_org_id.reset(token)

    lines = [r.getMessage() for r in caplog.records if "[CLINICMD] call" in r.getMessage()]
    assert "org_id=org-explicit" in lines[0]
    assert "org_id=org-ctx" in lines[1] and "branch_id=branch-1" in lines[1]
    assert "org_id=org-ctx" in lines[2]
