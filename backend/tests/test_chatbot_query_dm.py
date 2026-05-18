"""
IG-6 regression guard: _process_ecommerce_message must persist a [products_shown: ...]
manifest to the DB-backed history whenever the agent turn yields products.

Without the manifest, the agent's "extract product_id from [product_id:XXX] markers
in conversation history" instruction (chatbot_query.py:147) has no markers on the
carousel-display path — only the carousel-button postback path synthesises them.
This causes typed add-to-cart ("add white silk shirt to cart") to return "chaina"
even when the product was visible in the preceding carousel.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_products(n=2):
    return [
        {"id": f"prod-{i}", "name": f"Product {i}", "price": 1000 * i}
        for i in range(1, n + 1)
    ]


def _make_service():
    """Return a ChatbotQueryService with all external deps mocked out."""
    from app.services.chatbot_query import ChatbotQueryService

    svc = ChatbotQueryService.__new__(ChatbotQueryService)

    svc.conversation_service = MagicMock()
    svc.conversation_service.get_history = AsyncMock(return_value=[])
    svc.conversation_service.add_message = AsyncMock()

    svc.llm_service = MagicMock()

    return svc


def _make_agent_stream(*events):
    """Return an async generator that yields the given event dicts."""
    async def _gen(*args, **kwargs):
        for e in events:
            yield e
    return _gen


def _make_channel(channel_id="ch-1"):
    ch = MagicMock()
    ch.id = channel_id
    ch.config = {}
    return ch


def _make_customer(site_id="kasa"):
    c = MagicMock()
    c.id = "cust-uuid"
    c.site_id = site_id
    return c


async def _call(svc, events, *, sender_id="user-1", message_text="test"):
    with patch.object(svc, "_get_agent_service") as mock_get_agent:
        mock_agent = MagicMock()
        mock_agent.process_agent_stream = _make_agent_stream(*events)
        mock_get_agent.return_value = mock_agent

        with patch("app.services.chatbot_query.detect_language", return_value="en"):
            return await svc._process_ecommerce_message(
                db=AsyncMock(),
                customer=_make_customer(),
                channel=_make_channel(),
                sender_id=sender_id,
                message_text=message_text,
                brand_name="Kasa",
                supported_languages=["en"],
                start=0.0,
            )


# ---------------------------------------------------------------------------
# Case 1 — manifest present when products yielded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_product_manifest_written_to_db_when_products_yielded():
    """When the agent yields products, persisted message must contain [products_shown: ...]."""
    svc = _make_service()
    products = _make_products(2)

    events = [
        {"type": "products", "data": products},
        {"type": "done", "answer": "Here are some shirt options!", "suggestions": []},
    ]

    await _call(svc, events, sender_id="user-123", message_text="shirt heru dekhau")

    persisted = svc.conversation_service.add_message.call_args[0][4]
    assert "[products_shown:" in persisted
    assert "prod-1=Product 1" in persisted
    assert "prod-2=Product 2" in persisted


# ---------------------------------------------------------------------------
# Case 2 — manifest absent from user-facing answer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_facing_answer_has_no_manifest():
    """The answer returned to outbound_messaging must NOT contain [products_shown:]."""
    svc = _make_service()
    products = _make_products(1)

    events = [
        {"type": "products", "data": products},
        {"type": "done", "answer": "Check this out!", "suggestions": []},
    ]

    result = await _call(svc, events, sender_id="user-456", message_text="show me shirts")

    assert "[products_shown:" not in result["answer"]


# ---------------------------------------------------------------------------
# Case 3 — no manifest when zero products
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_manifest_when_no_products_yielded():
    """A turn with no product events must persist answer unchanged."""
    svc = _make_service()

    events = [
        {"type": "done", "answer": "Your cart has 2 items.", "suggestions": []},
    ]

    await _call(svc, events, sender_id="user-789", message_text="cart herau")

    persisted = svc.conversation_service.add_message.call_args[0][4]
    assert "[products_shown:" not in persisted
    assert persisted == "Your cart has 2 items."


# ---------------------------------------------------------------------------
# Case 4 — defensive: products with missing IDs are skipped, not written as orphans
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_products_missing_ids_are_skipped_in_manifest():
    """Products without an 'id' key must be omitted; no '=Name' or 'id=' orphans."""
    svc = _make_service()
    products = [
        {"id": "valid-id", "name": "Good Shirt"},
        {"name": "No ID Shirt"},        # missing key — must be skipped
        {"id": "", "name": "Empty ID"}, # falsy id — must be skipped
    ]

    events = [
        {"type": "products", "data": products},
        {"type": "done", "answer": "Here you go!", "suggestions": []},
    ]

    await _call(svc, events, sender_id="user-999", message_text="show products")

    persisted = svc.conversation_service.add_message.call_args[0][4]
    assert "valid-id=Good Shirt" in persisted
    assert "No ID Shirt" not in persisted
    assert "Empty ID" not in persisted
    assert "=No ID Shirt" not in persisted
