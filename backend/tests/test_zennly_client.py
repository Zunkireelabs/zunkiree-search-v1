"""
ZennlyClient mocked with httpx.MockTransport — no test hits real Zennly.
Mirrors test_clinicmd_client.py's pattern: patches httpx.AsyncClient itself so
the client's real _get/_post_rpc/insert_booking code runs unmodified against
the fake transport.
"""
import json

import httpx
import pytest

from app.services.zennly_client import ZennlyClient, ZennlyError


def _install_handler(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.fixture
def client():
    return ZennlyClient(base_url="https://fake.supabase.co", anon_key="anon-test-key")


@pytest.mark.asyncio
async def test_get_org_sends_apikey_and_bearer_and_parses_industries_vocab(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json=[{
                "id": "org-1", "name": "Sami's Brows and Lashes", "slug": "sbal",
                "industry_type": "salon",
                "industries": {
                    "staff_label": "Artist", "staff_label_plural": "Artists",
                    "location_label": "Room", "location_label_plural": "Rooms",
                    "enable_rooms": True,
                },
            }],
        )

    _install_handler(monkeypatch, handler)
    org = await client.get_org("sbal")

    assert org["id"] == "org-1"
    assert org["staff_label_plural"] == "Artists"
    assert org["location_label_plural"] == "Rooms"
    assert seen["headers"]["apikey"] == "anon-test-key"
    assert seen["headers"]["authorization"] == "Bearer anon-test-key"
    assert "slug=eq.sbal" in seen["url"]


@pytest.mark.asyncio
async def test_get_org_defaults_vocab_when_no_industries_row(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": "org-2", "name": "X", "slug": "x", "industries": None}])

    _install_handler(monkeypatch, handler)
    org = await client.get_org("x")
    assert org["staff_label_plural"] == "staff"
    assert org["location_label_plural"] == "rooms"


@pytest.mark.asyncio
async def test_get_org_returns_none_when_empty(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    _install_handler(monkeypatch, client and handler)
    assert await client.get_org("nope") is None


@pytest.mark.asyncio
async def test_list_treatments_requires_org_slug_resolved_first(client):
    with pytest.raises(ZennlyError) as exc_info:
        await client.list_treatments("org-never-resolved")
    assert exc_info.value.code == "ORG_SLUG_UNRESOLVED"


@pytest.mark.asyncio
async def test_list_treatments_calls_public_rpc_with_slug_and_maps_fields(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/rest/v1/organizations" in str(request.url):
            return httpx.Response(200, json=[{"id": "org-1", "name": "SBAL", "slug": "sbal", "industries": None}])
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        return httpx.Response(200, json=[{
            "id": "svc-1", "name": "Eyebrow Threading", "duration_minutes": 20,
            "price_npr": 500, "effective_price_npr": 400, "description": "d",
            "category_name": "brows", "is_on_offer": True,
        }])

    _install_handler(monkeypatch, handler)
    await client.get_org("sbal")
    services = await client.list_treatments("org-1")

    assert seen["path"] == "/rest/v1/rpc/public_get_bookable_services"
    assert seen["body"] == {"p_org_slug": "sbal"}
    assert services == [{
        "id": "svc-1", "name": "Eyebrow Threading", "duration_minutes": 20,
        "price_npr": 400, "description": "d", "category": "brows",
    }]


@pytest.mark.asyncio
async def test_list_treatments_cleans_whole_number_float_price(monkeypatch, client):
    """SBAL-Z3 P4: Postgres numeric comes back as 3499.0 for a whole-NPR
    price — list_treatments must hand back 3499 (int), not the float, so
    nothing downstream (cards, text, the model's own narration) ever shows
    the "NPR 3499.0" artifact."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "/rest/v1/organizations" in str(request.url):
            return httpx.Response(200, json=[{"id": "org-1", "name": "SBAL", "slug": "sbal", "industries": None}])
        return httpx.Response(200, json=[{
            "id": "svc-1", "name": "Brow Lamination", "duration_minutes": 60,
            "effective_price_npr": 3499.0, "description": "d", "category_name": "brows",
        }])

    _install_handler(monkeypatch, handler)
    await client.get_org("sbal")
    services = await client.list_treatments("org-1")

    assert services[0]["price_npr"] == 3499
    assert isinstance(services[0]["price_npr"], int)


@pytest.mark.asyncio
async def test_list_treatments_filters_excluded_categories(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/rest/v1/organizations" in str(request.url):
            return httpx.Response(200, json=[{"id": "org-1", "name": "SBAL", "slug": "sbal", "industries": None}])
        return httpx.Response(200, json=[
            {"id": "s1", "name": "A", "category_name": "brows", "effective_price_npr": 1},
            {"id": "s2", "name": "B", "category_name": "lashes", "effective_price_npr": 2},
        ])

    _install_handler(monkeypatch, handler)
    await client.get_org("sbal")
    services = await client.list_treatments("org-1", branch={"excluded_service_categories": ["lashes"]})
    assert [s["id"] for s in services] == ["s1"]


@pytest.mark.asyncio
async def test_list_chairs_reads_rooms_table(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"id": "room-1", "name": "Room A", "capacity": 2}])

    _install_handler(monkeypatch, handler)
    rooms = await client.list_chairs("branch-1")
    assert "/rest/v1/rooms" in seen["url"]
    assert "branch_id=eq.branch-1" in seen["url"]
    assert rooms == [{"id": "room-1", "name": "Room A", "capacity": 2}]


@pytest.mark.asyncio
async def test_bookings_range_remaps_room_id_to_chair_id(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        return httpx.Response(200, json=[
            {"booking_date": "2026-10-10", "start_time": "10:00:00", "duration_minutes": 30, "room_id": "room-1"},
        ])

    _install_handler(monkeypatch, handler)
    rows = await client.bookings_range("branch-1", "2026-10-10", "2026-10-10")

    assert seen["path"] == "/rest/v1/rpc/public_check_branch_bookings_range"
    assert seen["body"] == {"p_branch_id": "branch-1", "p_start_date": "2026-10-10", "p_end_date": "2026-10-10"}
    assert rows[0]["chair_id"] == "room-1"
    assert rows[0]["room_id"] == "room-1"


@pytest.mark.asyncio
async def test_insert_booking_sends_return_minimal(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["prefer"] = request.headers.get("prefer")
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        return httpx.Response(201)

    _install_handler(monkeypatch, handler)
    row = {"client_request_id": "req-1", "branch_id": "b1", "date": "2026-10-10", "start_time": "10:00", "created_by": None}
    await client.insert_booking(row)

    assert seen["path"] == "/rest/v1/bookings"
    assert seen["prefer"] == "return=minimal"
    assert seen["body"]["client_request_id"] == "req-1"
    assert seen["body"]["created_by"] is None


@pytest.mark.asyncio
async def test_get_booking_calls_request_id_rpc(monkeypatch, client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        return httpx.Response(200, json=[{"booking_number": "BK-1", "date": "2026-10-10", "start_time": "10:00:00"}])

    _install_handler(monkeypatch, handler)
    booking = await client.get_booking("req-1")

    assert seen["path"] == "/rest/v1/rpc/public_get_booking_by_request_id"
    assert seen["body"] == {"p_client_request_id": "req-1"}
    assert booking["booking_number"] == "BK-1"


@pytest.mark.asyncio
async def test_upsert_customer_reuses_existing_match(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/v1/rpc/find_customer_for_booking"
        return httpx.Response(200, json=[{"id": "cust-existing", "gender": None}])

    _install_handler(monkeypatch, handler)
    result = await client.upsert_customer("org-1", "branch-1", "Jane Doe", "+9779841234567", None, None)
    assert result == "cust-existing"


@pytest.mark.asyncio
async def test_upsert_customer_creates_new_when_no_match(monkeypatch, client):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/rest/v1/rpc/find_customer_for_booking":
            return httpx.Response(200, json=[])
        return httpx.Response(201, json=[{"id": "cust-new"}])

    _install_handler(monkeypatch, handler)
    result = await client.upsert_customer("org-1", "branch-1", "Jane Doe", "+9779841234567", None, None)
    assert result == "cust-new"
    assert calls == ["/rest/v1/rpc/find_customer_for_booking", "/rest/v1/customers"]


@pytest.mark.asyncio
async def test_upsert_customer_failure_is_non_blocking(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": "23505", "message": "conflict"})

    _install_handler(monkeypatch, handler)
    result = await client.upsert_customer("org-1", "branch-1", "Jane Doe", "+9779841234567", None, None)
    assert result is None


@pytest.mark.asyncio
async def test_raise_for_status_extracts_postgres_error_code(monkeypatch, client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"code": "P0005", "message": "branch full"})

    _install_handler(monkeypatch, handler)
    with pytest.raises(ZennlyError) as exc_info:
        await client.bookings_range("branch-1", "2026-10-10", "2026-10-10")
    assert exc_info.value.pg_code == "P0005"


def test_get_zennly_client_raises_when_not_configured(monkeypatch):
    from app.services import zennly_client as mod

    monkeypatch.setattr(mod, "_zennly_client", None)

    class FakeSettings:
        zennly_supabase_url = None
        zennly_supabase_anon_key = None

    monkeypatch.setattr(mod, "get_settings", lambda: FakeSettings())

    with pytest.raises(mod.ZennlyNotConfigured):
        mod.get_zennly_client()
