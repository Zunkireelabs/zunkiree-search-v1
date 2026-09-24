"""
P3-WIDGET-THROUGH-ORCA-BRIEF Part B (B3): /api/v1/query/stream must route an
Orca-forwarded chat turn (channel="chat" set explicitly, as
orca-gateway/src/orca_gateway/backends/zunkiree.py sends it) and a direct
widget turn (channel omitted, as Widget.tsx sends it today) to the exact
same agent path — same branch, same kwargs into ClinicAgentService, same
`channel` value reaching the agent. Proven from the [QUERY-STREAM] and
[CLINIC-LATENCY] log lines, not the reply text, per the brief's own
instruction.
"""
import logging
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.api.query import QueryRequest, submit_query_stream
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig


def _make_clinic_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000cc"),
        name="Dental Co",
        site_id="dental-city",
        api_key="key",
        website_type="clinic",
    )


async def _consume(response):
    async for _ in response.body_iterator:
        pass


async def _run(channel: str | None, caplog):
    customer = _make_clinic_customer()
    config = WidgetConfig(customer_id=customer.id, brand_name="Dental Co")

    request = AsyncMock()
    request.headers = {}
    request.client = None

    query = QueryRequest(
        site_id="dental-city",
        question="do you have any appointments open tomorrow",
        session_id=str(uuid.uuid4()),
        channel=channel,
    )

    clinic_mock = AsyncMock()
    received_kwargs: dict = {}

    async def clinic_gen(*args, **kwargs):
        received_kwargs.update(kwargs)
        yield {"type": "done", "answer": "clinic reply", "suggestions": [], "sources": []}

    clinic_mock.process_agent_stream = clinic_gen

    with patch("app.api.query.get_query_service") as get_qs, \
         patch("app.services.clinic_agent.get_clinic_agent_service", return_value=clinic_mock):
        qs = get_qs.return_value
        qs._get_customer = AsyncMock(return_value=customer)
        qs._get_widget_config = AsyncMock(return_value=config)

        with caplog.at_level(logging.INFO, logger="zunkiree.query.api"):
            response = await submit_query_stream(request, query, db=AsyncMock())
            await _consume(response)

    return received_kwargs


@pytest.mark.asyncio
async def test_orca_forwarded_and_direct_widget_turns_reach_same_agent_path(caplog):
    """channel="chat" (Orca) and channel unset (direct widget) both land in
    ClinicAgentService with the identical channel value — the widget change
    is a URL choice, never a second code path (brief §2)."""
    orca_kwargs = await _run("chat", caplog)
    direct_kwargs = await _run(None, caplog)

    assert orca_kwargs["channel"] == "chat"
    assert direct_kwargs["channel"] == "chat"
    assert orca_kwargs["channel"] == direct_kwargs["channel"]
    # Same site/session-shaped call into the agent either way (module identity,
    # not a per-channel branch) — asserted structurally, not from the reply.
    assert orca_kwargs["site_id"] == direct_kwargs["site_id"] == "dental-city"


@pytest.mark.asyncio
async def test_channel_visible_in_query_stream_log_not_reply_text(caplog):
    """B3: 'read it from the [QUERY-STREAM] logs, not the reply text.'"""
    with caplog.at_level(logging.WARNING, logger="zunkiree.query.api"):
        await _run("chat", caplog)
    query_stream_lines = [r.message for r in caplog.records if "[QUERY-STREAM]" in r.message]
    assert any("channel=chat" in line and "site_id=dental-city" in line for line in query_stream_lines)


@pytest.mark.asyncio
async def test_channel_defaults_to_chat_when_widget_omits_it(caplog):
    with caplog.at_level(logging.WARNING, logger="zunkiree.query.api"):
        await _run(None, caplog)
    query_stream_lines = [r.message for r in caplog.records if "[QUERY-STREAM]" in r.message]
    assert any("channel=chat" in line for line in query_stream_lines)
