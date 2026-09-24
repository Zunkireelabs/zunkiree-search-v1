"""
P2 brief §7c B4 item 2 + tests requirement: once the OpenAI client is bounded
(test_openai_client.py), a stalled embeddings call now raises instead of
hanging. This asserts the two things that matter once it raises:

1. The DB session was already committed/released *before* the embeddings
   call, not held idle-in-transaction across it (item 2's fix).
2. The exception propagates cleanly out of process_query_stream rather than
   being swallowed — api/query.py's outer `except Exception` (unit-tested
   indirectly here by asserting the same exception surfaces) is what turns
   that into a clean SSE `error` event for the client.
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import openai
import pytest

from app.services.query import QueryService


def _make_customer():
    customer = MagicMock()
    customer.id = uuid4()
    customer.website_type = "generic"
    return customer


@pytest.mark.asyncio
async def test_stalled_embedding_call_releases_session_then_raises():
    service = QueryService()
    customer = _make_customer()

    db = AsyncMock()
    call_order = []
    db.commit.side_effect = lambda: call_order.append("db.commit")

    service._get_customer = AsyncMock(return_value=customer)
    service._validate_origin = AsyncMock(return_value=True)
    service._get_widget_config = AsyncMock(return_value=None)
    service._get_business_profile = AsyncMock(return_value=None)

    timeout_error = openai.APITimeoutError(request=MagicMock())

    async def stalled_create_embedding(question):
        call_order.append("create_embedding")
        raise timeout_error

    service.embedding_service.create_embedding = stalled_create_embedding

    with pytest.raises(openai.APITimeoutError):
        async for _event in service.process_query_stream(db=db, site_id="dental-city", question="hi"):
            pass

    # The session was released (committed) before the bounded call was even
    # attempted, not held open across it.
    assert call_order == ["db.commit", "create_embedding"]


@pytest.mark.asyncio
async def test_healthy_embedding_call_is_unaffected():
    """Sanity check the commit-before-retrieval change doesn't break the
    happy path: retrieval still runs and reaches the no-data short-circuit
    (no ingested content) using the customer's real id."""
    service = QueryService()
    customer = _make_customer()

    db = AsyncMock()
    service._get_customer = AsyncMock(return_value=customer)
    service._validate_origin = AsyncMock(return_value=True)
    service._get_widget_config = AsyncMock(return_value=None)
    service._get_business_profile = AsyncMock(return_value=None)
    service._check_ingestion_status = AsyncMock(return_value="empty")

    service.embedding_service.create_embedding = AsyncMock(return_value=[0.0] * 8)
    service.vector_store.query_vectors = AsyncMock(return_value=[])
    service._keyword_search = AsyncMock(return_value=[])

    events = [event async for event in service.process_query_stream(db=db, site_id="dental-city", question="hi")]

    assert db.commit.await_count >= 1
    assert events[-1]["type"] == "done"
