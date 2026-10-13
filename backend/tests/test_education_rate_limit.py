"""One visitor must not be able to send unlimited education messages: every message can cost an AI call. The limiter is a
small in-process rolling window per (tenant, visitor address); other tenant types are never limited. Production runs two
workers that count separately, so the real ceiling is up to twice the number here."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.query import QueryRequest, submit_query_stream
from app.api.widget import get_widget_history
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.utils.rate_limit import CHAT_LIMIT, HISTORY_LIMIT, RateLimiter, client_ip, reset_rate_limits

SITE = "edu-rate-test"


@pytest.fixture(autouse=True)
def _fresh():
    reset_rate_limits()
    yield
    reset_rate_limits()


# --- the limiter itself ---------------------------------------------------------------------------------------------

def test_allows_up_to_the_limit_then_blocks():
    now = [100.0]
    rl = RateLimiter(clock=lambda: now[0])
    assert all(rl.hit("k", 3, 60) is None for _ in range(3))
    wait = rl.hit("k", 3, 60)
    assert wait is not None and 1 <= wait <= 60


def test_visitors_are_counted_separately():
    rl = RateLimiter(clock=lambda: 0.0)
    for _ in range(3):
        rl.hit("a", 3, 60)
    assert rl.hit("a", 3, 60) is not None
    assert rl.hit("b", 3, 60) is None


def test_window_rolls_so_the_visitor_can_send_again():
    now = [0.0]
    rl = RateLimiter(clock=lambda: now[0])
    for _ in range(3):
        rl.hit("k", 3, 60)
    assert rl.hit("k", 3, 60) is not None
    now[0] = 61.0
    assert rl.hit("k", 3, 60) is None


def test_blocked_attempts_do_not_extend_the_block():
    now = [0.0]
    rl = RateLimiter(clock=lambda: now[0])
    for _ in range(3):
        rl.hit("k", 3, 60)
    for t in range(1, 50):
        now[0] = float(t)
        rl.hit("k", 3, 60)       # hammering while blocked
    now[0] = 61.0
    assert rl.hit("k", 3, 60) is None


def test_idle_keys_are_dropped_so_memory_does_not_grow():
    now = [0.0]
    rl = RateLimiter(clock=lambda: now[0])
    for i in range(50):
        rl.hit(f"ip{i}", 3, 60)
    now[0] = 1000.0
    rl.hit("fresh", 3, 60)
    assert len(rl._hits) == 1


def test_client_ip_uses_the_address_the_proxy_added_not_one_the_client_wrote():
    req = SimpleNamespace(headers={"x-forwarded-for": "6.6.6.6, 203.0.113.9"}, client=SimpleNamespace(host="10.0.0.2"))
    assert client_ip(req) == "203.0.113.9"      # a script cannot dodge the limit by inventing the first entry
    assert client_ip(SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.2"))) == "10.0.0.2"
    assert client_ip(SimpleNamespace(headers={}, client=None)) == "unknown"


def test_the_numbers_are_the_agreed_ones():
    assert CHAT_LIMIT == 20 and HISTORY_LIMIT == 60


# --- the routes -----------------------------------------------------------------------------------------------------

def _customer(website_type="education"):
    return Customer(id=uuid.UUID("00000000-0000-0000-0000-0000000000ed"), name="Edu", site_id=SITE, api_key="k",
                    website_type=website_type)


def _agent():
    agent = MagicMock()
    agent.calls = 0

    async def gen(**kw):
        agent.calls += 1
        yield {"type": "done", "answer": "ok", "suggestions": [], "sources": []}
    agent.process_agent_stream = gen
    return agent


async def _send(agent, ip="203.0.113.9", website_type="education", session="s1"):
    customer = _customer(website_type)
    request = AsyncMock()
    request.headers, request.client = {"x-forwarded-for": ip}, SimpleNamespace(host="10.0.0.2")
    with patch("app.api.query.get_query_service") as qs, \
         patch("app.api.query.require_allowed_origin", AsyncMock()), \
         patch("app.services.education_agent.get_education_agent_service", return_value=agent), \
         patch("app.services.clinic_agent.get_clinic_agent_service", return_value=agent):
        qs.return_value._get_customer = AsyncMock(return_value=customer)
        qs.return_value._get_widget_config = AsyncMock(return_value=WidgetConfig(customer_id=customer.id, brand_name="Edu"))
        response = await submit_query_stream(request, QueryRequest(site_id=SITE, question="hello", session_id=session), db=AsyncMock())
        "".join([c async for c in response.body_iterator])


@pytest.mark.asyncio
async def test_the_21st_message_in_a_minute_is_refused_before_the_ai_runs():
    agent = _agent()
    for _ in range(CHAT_LIMIT):
        await _send(agent)
    with pytest.raises(HTTPException) as e:
        await _send(agent)
    assert e.value.status_code == 429 and e.value.detail["code"] == "RATE_LIMITED"
    assert int(e.value.headers["Retry-After"]) >= 1
    assert agent.calls == CHAT_LIMIT


@pytest.mark.asyncio
async def test_a_new_session_id_does_not_reset_the_count():
    agent = _agent()
    for i in range(CHAT_LIMIT):
        await _send(agent, session=f"s{i}")
    with pytest.raises(HTTPException) as e:
        await _send(agent, session="brand-new")
    assert e.value.status_code == 429


@pytest.mark.asyncio
async def test_another_visitor_is_not_affected():
    agent = _agent()
    for _ in range(CHAT_LIMIT):
        await _send(agent)
    await _send(agent, ip="198.51.100.7")
    assert agent.calls == CHAT_LIMIT + 1


@pytest.mark.asyncio
async def test_other_tenant_types_are_never_limited():
    agent = _agent()
    for _ in range(CHAT_LIMIT + 5):
        await _send(agent, website_type="clinic")
    assert agent.calls == CHAT_LIMIT + 5


@pytest.mark.asyncio
async def test_history_is_limited_more_loosely():
    from app.services.query import QueryService
    from app.database import get_db
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import widget_router

    found = MagicMock()
    found.scalar_one_or_none.return_value = _customer()
    db = SimpleNamespace(execute=AsyncMock(return_value=found))
    app = FastAPI()
    app.include_router(widget_router, prefix="/api/v1")

    async def fake_db():
        yield db
    app.dependency_overrides[get_db] = fake_db
    hdr = {"x-forwarded-for": "203.0.113.9"}
    with patch("app.api.widget.get_query_service", return_value=QueryService()), \
         patch("app.api.widget.require_allowed_origin", AsyncMock()), \
         patch("app.services.education_memory.DbEducationMemory.list_messages", AsyncMock(return_value=[])), \
         patch("app.services.education_memory.DbEducationMemory.load_profile", AsyncMock(return_value={"contact": {}, "shown": {}})):
        client = TestClient(app)
        codes = [client.get(f"/api/v1/widget/history/{SITE}/s1", headers=hdr).status_code for _ in range(HISTORY_LIMIT + 1)]
    assert codes[:HISTORY_LIMIT] == [200] * HISTORY_LIMIT and codes[-1] == 429
