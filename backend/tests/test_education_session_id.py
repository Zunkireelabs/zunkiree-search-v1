"""Education turns are keyed by (tenant, session_id), so a missing or blank session id must be refused: before this check
every education visitor without one shared the "" profile, and a second visitor's counselor form came back prefilled with
the first visitor's name, email and phone. Ids are not forced to be UUIDs (the widget sends crypto.randomUUID(), other
callers may not); they only have to be non-blank and fit the 100-char session_id column. Other website types are untouched."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.query import QueryRequest, submit_query_stream
from app.api.widget import get_widget_history
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig

SITE = "edu-session-test"


def _customer(website_type: str) -> Customer:
    return Customer(id=uuid.UUID("00000000-0000-0000-0000-0000000000ed"), name="Edu", site_id=SITE, api_key="k",
                    website_type=website_type)


def _agent():
    agent = MagicMock()
    agent.seen = []

    async def gen(**kw):
        agent.seen.append(kw["session_id"])
        yield {"type": "done", "answer": "ok", "suggestions": [], "sources": []}
    agent.process_agent_stream = gen
    return agent


async def _stream(session_id, website_type="education"):
    customer, agent = _customer(website_type), _agent()
    request = AsyncMock()
    request.headers, request.client = {}, None
    with patch("app.api.query.get_query_service") as qs, \
         patch("app.services.education_agent.get_education_agent_service", return_value=agent), \
         patch("app.services.clinic_agent.get_clinic_agent_service", return_value=agent):
        qs.return_value._get_customer = AsyncMock(return_value=customer)
        qs.return_value._get_widget_config = AsyncMock(return_value=WidgetConfig(customer_id=customer.id, brand_name="Edu"))
        response = await submit_query_stream(request, QueryRequest(site_id=SITE, question="talk to a counselor",
                                                                   session_id=session_id), db=AsyncMock())
        "".join([c async for c in response.body_iterator])
    return agent.seen


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", [None, "", "   ", "x" * 101])
async def test_education_stream_rejects_missing_blank_or_oversized_session_id(session_id):
    with pytest.raises(HTTPException) as e:
        await _stream(session_id)
    assert e.value.status_code == 400
    assert e.value.detail["code"] == "INVALID_SESSION_ID"


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", [str(uuid.uuid4()), "orca-call-123", "x" * 100])
async def test_education_stream_accepts_valid_session_id_unchanged(session_id):
    assert await _stream(session_id) == [session_id]   # the agent gets exactly the id the caller sent


@pytest.mark.asyncio
async def test_other_website_types_still_accept_no_session_id():
    assert await _stream(None, website_type="clinic") == [""]


def _db_returning(customer):
    result = MagicMock()
    result.scalar_one_or_none.return_value = customer
    return SimpleNamespace(execute=AsyncMock(return_value=result))


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", ["", "   ", "x" * 101])
async def test_education_history_rejects_blank_or_oversized_session_id(session_id):
    with pytest.raises(HTTPException) as e:
        await get_widget_history(SITE, session_id, _db_returning(_customer("education")))
    assert e.value.status_code == 400
    assert e.value.detail["code"] == "INVALID_SESSION_ID"
