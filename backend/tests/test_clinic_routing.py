"""
ZUNKIREE-CLINIC-AGENT-BRIEF §7: website_type="clinic" reaches ClinicAgentService;
hospitality/ecommerce unchanged.
"""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.api.query import QueryRequest, submit_query_stream
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig


def _make_customer(website_type: str) -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000bb"),
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


async def _run_routing_test(website_type: str):
    customer = _make_customer(website_type)
    config = WidgetConfig(customer_id=customer.id, brand_name="Test Co")

    request = AsyncMock()
    request.headers = {}
    request.client = None

    query = QueryRequest(site_id="test-site", question="What services do you offer?", session_id=None)

    clinic_mock = AsyncMock()
    async def clinic_gen(*a, **kw):
        yield {"type": "done", "answer": "clinic", "suggestions": [], "sources": []}
    clinic_mock.process_agent_stream = clinic_gen

    hospitality_mock = AsyncMock()
    async def hospitality_gen(*a, **kw):
        yield {"type": "done", "answer": "hospitality", "suggestions": [], "sources": []}
    hospitality_mock.process_agent_stream = hospitality_gen

    ecommerce_mock = AsyncMock()
    async def ecommerce_gen(*a, **kw):
        yield {"type": "done", "answer": "ecommerce", "suggestions": [], "sources": []}
    ecommerce_mock.process_agent_stream = ecommerce_gen

    with patch("app.api.query.get_query_service") as get_qs, \
         patch("app.services.clinic_agent.get_clinic_agent_service", return_value=clinic_mock) as get_clinic, \
         patch("app.services.hospitality_agent.get_hospitality_agent_service", return_value=hospitality_mock) as get_hosp, \
         patch("app.services.agent.get_agent_service", return_value=ecommerce_mock) as get_ecom:
        qs = get_qs.return_value
        qs._get_customer = AsyncMock(return_value=customer)
        qs._get_widget_config = AsyncMock(return_value=config)

        response = await submit_query_stream(request, query, db=AsyncMock())
        body = await _consume(response)

    return body, get_clinic, get_hosp, get_ecom


@pytest.mark.asyncio
async def test_clinic_website_type_routes_to_clinic_agent():
    body, get_clinic, get_hosp, get_ecom = await _run_routing_test("clinic")
    assert get_clinic.called
    assert not get_hosp.called
    assert not get_ecom.called
    assert '"answer": "clinic"' in body


@pytest.mark.asyncio
async def test_hospitality_website_type_unchanged():
    body, get_clinic, get_hosp, get_ecom = await _run_routing_test("hospitality")
    assert get_hosp.called
    assert not get_clinic.called
    assert not get_ecom.called


@pytest.mark.asyncio
async def test_ecommerce_website_type_unchanged():
    body, get_clinic, get_hosp, get_ecom = await _run_routing_test("ecommerce")
    assert get_ecom.called
    assert not get_clinic.called
    assert not get_hosp.called
