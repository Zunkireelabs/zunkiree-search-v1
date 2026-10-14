"""Only a tenant's approved websites may use its education chat. Other chat types already refuse an unapproved Origin
(QueryService._validate_origin); the education branch of /query/stream returned before that check and /widget/history never
had it, so any website could embed an education tenant's chatbot and spend its AI budget. A request with no Origin header
(server to server, same-origin) is let through, exactly as on the other paths; this is a browser-side control."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.query import QueryRequest, submit_query_stream
from app.api.widget import get_widget_history
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.query import QueryService

SITE = "edu-origin-test"
OK = {"origin": "https://admizz.example"}
BAD = {"origin": "https://evil.example"}


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


def _db_with_domains(*domains):
    """A db whose domains table holds `domains` (what _validate_origin reads)."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = [SimpleNamespace(domain=d) for d in domains]
    return SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock())


async def _stream(headers, website_type="education", domains=("admizz.example",)):
    customer, agent, db = _customer(website_type), _agent(), _db_with_domains(*domains)
    request = AsyncMock()
    request.headers, request.client = headers, None
    service = QueryService()   # the real origin rule; only the tenant lookups are faked
    service._get_customer = AsyncMock(return_value=customer)
    service._get_widget_config = AsyncMock(return_value=WidgetConfig(customer_id=customer.id, brand_name="Edu"))
    with patch("app.api.query.get_query_service", return_value=service), \
         patch("app.services.education_agent.get_education_agent_service", return_value=agent), \
         patch("app.services.clinic_agent.get_clinic_agent_service", return_value=agent):
        response = await submit_query_stream(request, QueryRequest(site_id=SITE, question="hello", session_id="s1"), db=db)
        "".join([c async for c in response.body_iterator])
    return agent.calls


@pytest.mark.asyncio
async def test_stream_refuses_a_website_that_is_not_approved():
    with pytest.raises(HTTPException) as e:
        await _stream(BAD)
    assert e.value.status_code == 403 and e.value.detail["code"] == "ORIGIN_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_stream_does_not_run_the_agent_for_a_refused_website():
    agent_calls = []
    try:
        await _stream(BAD)
    except HTTPException:
        pass
    else:
        agent_calls.append("ran")
    assert agent_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    OK,                                              # approved website
    {"origin": "https://www.admizz.example"},        # www variant of an approved website
    {"origin": "http://localhost:5173"},             # local development
    {},                                              # no Origin header: server to server / same origin
])
async def test_stream_serves_approved_or_header_less_requests(headers):
    assert await _stream(headers) == 1


@pytest.mark.asyncio
async def test_stream_refuses_every_website_when_the_approved_list_is_empty():
    with pytest.raises(HTTPException) as e:
        await _stream(OK, domains=())
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_other_tenant_types_are_unchanged_by_this_check():
    assert await _stream(BAD, website_type="clinic") == 1   # this guard is education-only


def _history_db(customer, domains=("admizz.example",)):
    found = MagicMock()
    found.scalar_one_or_none.return_value = customer
    listed = MagicMock()
    listed.scalars.return_value.all.return_value = [SimpleNamespace(domain=d) for d in domains]
    return SimpleNamespace(execute=AsyncMock(side_effect=[found, listed, listed]))


async def _history(headers, domains=("admizz.example",)):
    request = SimpleNamespace(headers=headers)
    service = QueryService()
    msgs = [{"id": "1", "role": "assistant", "content": "hi", "blocks": [], "created_at": "t"}]
    with patch("app.api.widget.get_query_service", return_value=service), \
         patch("app.services.education_memory.DbEducationMemory.list_messages", AsyncMock(return_value=msgs)) as listed, \
         patch("app.services.education_memory.DbEducationMemory.load_profile", AsyncMock(return_value={"contact": {}, "shown": {}})):
        out = await get_widget_history(SITE, "s1", _history_db(_customer(), domains), request=request)
    return out, listed


@pytest.mark.asyncio
async def test_history_refuses_a_website_that_is_not_approved_and_reads_nothing():
    with patch("app.services.education_memory.DbEducationMemory.list_messages", AsyncMock()) as listed:
        with pytest.raises(HTTPException) as e:
            await get_widget_history(SITE, "s1", _history_db(_customer()), request=SimpleNamespace(headers=BAD))
    assert e.value.status_code == 403 and e.value.detail["code"] == "ORIGIN_NOT_ALLOWED"
    listed.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [OK, {"origin": "http://localhost:5173"}, {}])
async def test_history_serves_approved_or_header_less_requests(headers):
    out, _ = await _history(headers)
    assert out["messages"][0]["content"] == "hi"


@pytest.mark.parametrize("headers,status", [({"Origin": "https://evil.example"}, 403),
                                            ({"Origin": "https://admizz.example"}, 200), ({}, 200)])
def test_history_route_receives_the_origin_header_over_http(headers, status):
    """The direct calls above pass `request` by hand; this proves FastAPI hands the real request to the endpoint."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import widget_router
    from app.database import get_db

    db = _history_db(_customer())
    app = FastAPI()
    app.include_router(widget_router, prefix="/api/v1")

    async def fake_db():
        yield db
    app.dependency_overrides[get_db] = fake_db
    with patch("app.api.widget.get_query_service", return_value=QueryService()), \
         patch("app.services.education_memory.DbEducationMemory.list_messages", AsyncMock(return_value=[])), \
         patch("app.services.education_memory.DbEducationMemory.load_profile", AsyncMock(return_value={"contact": {}, "shown": {}})):
        assert TestClient(app).get(f"/api/v1/widget/history/{SITE}/s1", headers=headers).status_code == status
