"""
IG-6 regression guard: _process_ecommerce_message must persist a [products_shown: ...]
manifest to the DB-backed history whenever the agent turn yields products.

Without the manifest, the agent's "extract product_id from [products_shown] entries
in conversation history" instruction has no markers on the carousel-display path —
only the carousel-button postback path synthesises them. This causes typed add-to-cart
("add white silk shirt to cart") to return "chaina" even when the product was visible
in the preceding carousel.

IG-8 regression guards (appended): the manifest format must use the
product(id=…, name=…) wrapper syntax — not a bare comma-list — so the LLM cannot
misread the result count as the desired purchase quantity.
"""
import re
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
    assert "product(id=prod-1, name=Product 1)" in persisted
    assert "product(id=prod-2, name=Product 2)" in persisted


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
    assert "product(id=valid-id, name=Good Shirt)" in persisted
    assert "No ID Shirt" not in persisted
    assert "Empty ID" not in persisted
    assert "=No ID Shirt" not in persisted


# ---------------------------------------------------------------------------
# IG-8 guards — manifest format shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manifest_uses_product_wrapper_format():
    """
    IG-8: manifest entries must use product(id=…, name=…) syntax, not bare id=Name.
    The old comma-list format was the H4 vector: LLM read '2 products listed' as
    quantity=2. A regex pin locks the shape so future refactors can't silently revert.
    """
    svc = _make_service()
    products = _make_products(2)

    events = [
        {"type": "products", "data": products},
        {"type": "done", "answer": "Here are some options!", "suggestions": []},
    ]

    await _call(svc, events, sender_id="user-ig8", message_text="shirts dekhau")

    persisted = svc.conversation_service.add_message.call_args[0][4]
    assert re.search(r"\[products_shown: product\(id=[^,]+, name=[^)]+\)", persisted), (
        f"manifest must start with product(id=…, name=…) wrapper; got: {persisted!r}"
    )


@pytest.mark.asyncio
async def test_manifest_entries_separated_by_pipe_not_comma():
    """
    IG-8: multi-product manifests must use ' | ' as separator, not ', '.
    Comma-separated IDs looked like a CSV that the LLM could miscount as quantity.
    """
    svc = _make_service()
    products = _make_products(2)

    events = [
        {"type": "products", "data": products},
        {"type": "done", "answer": "Two options!", "suggestions": []},
    ]

    await _call(svc, events, sender_id="user-ig8b", message_text="shirts dekhau")

    persisted = svc.conversation_service.add_message.call_args[0][4]
    # Entries must be separated by pipe
    assert " | " in persisted
    # Old comma-list format must not appear between entries
    assert "Product 1, prod-2" not in persisted
    assert "Product 1, product(id=prod-2" not in persisted
