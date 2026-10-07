"""SBAL-Z4 bug found during stage verification: the generic greeting fast-path
in /query/stream intercepted bare "hi"/"hello" etc. BEFORE the website_type
== "clinic" routing check ever ran, so a clinic tenant's first "hi" never
reached ClinicAgentService — meaning assistant_name self-introduction could
never fire on the single most common first message. Clinic tenants must
skip this fast-path and always reach the agent; other website_types are
unaffected."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.api.query import QueryRequest, submit_query_stream
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig


def _make_customer(website_type: str) -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000cc"),
        name="Test Co",
        site_id="test-site",
        api_key="key",
        website_type=website_type,
    )


async def _consume(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return "".join(chunks)


@pytest.mark.asyncio
async def test_clinic_bare_greeting_reaches_clinic_agent_not_generic_template():
    customer = _make_customer("clinic")
    config = WidgetConfig(customer_id=customer.id, brand_name="Test Co")

    request = AsyncMock()
    request.headers = {}
    request.client = None

    query = QueryRequest(site_id="test-site", question="hi", session_id=None)

    clinic_mock = AsyncMock()
    async def clinic_gen(*a, **kw):
        yield {"type": "done", "answer": "clinic agent response", "suggestions": [], "sources": []}
    clinic_mock.process_agent_stream = clinic_gen

    with patch("app.api.query.get_query_service") as get_qs, \
         patch("app.services.clinic_agent.get_clinic_agent_service", return_value=clinic_mock) as get_clinic:
        qs = get_qs.return_value
        qs._get_customer = AsyncMock(return_value=customer)
        qs._get_widget_config = AsyncMock(return_value=config)

        response = await submit_query_stream(request, query, db=AsyncMock())
        body = await _consume(response)

    assert get_clinic.called
    assert '"answer": "clinic agent response"' in body
    assert "How can I help you today?" not in body


@pytest.mark.asyncio
async def test_non_clinic_bare_greeting_keeps_generic_template():
    customer = _make_customer("ecommerce")
    config = WidgetConfig(customer_id=customer.id, brand_name="Test Co")

    request = AsyncMock()
    request.headers = {}
    request.client = None

    query = QueryRequest(site_id="test-site", question="hi", session_id=None)

    ecommerce_mock = AsyncMock()
    async def ecommerce_gen(*a, **kw):
        yield {"type": "done", "answer": "ecommerce agent response", "suggestions": [], "sources": []}
    ecommerce_mock.process_agent_stream = ecommerce_gen

    with patch("app.api.query.get_query_service") as get_qs, \
         patch("app.services.agent.get_agent_service", return_value=ecommerce_mock) as get_ecom:
        qs = get_qs.return_value
        qs._get_customer = AsyncMock(return_value=customer)
        qs._get_widget_config = AsyncMock(return_value=config)

        response = await submit_query_stream(request, query, db=AsyncMock())
        body = await _consume(response)

    assert not get_ecom.called
    assert "Hi! I'm Test Co. How can I help you today?" in body
