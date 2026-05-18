"""
IG-8 regression guard: AgentService must not inflate cart quantity when the LLM
emits duplicate add_to_cart calls for the same (product_id, size) within one turn.

Covers the H2 hypothesis: two add_to_cart(qty=1) calls accumulate to qty=2 via the
additive cart semantics (cart.py:add_item increments on match). The dedup guard in
agent.py intercepts the second call and substitutes get_cart so the LLM receives
current cart state without re-adding.
"""
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

PRODUCT_ID = "06b0860f-6e97-4856-9234-730a3f4e49b5"
PRODUCT_ID_2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SIZE = "M"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _tool_call_chunk(index: int, call_id: str, name: str, args: dict):
    """Single streaming chunk carrying one tool-call delta."""
    chunk = MagicMock()
    choice = MagicMock()
    choice.finish_reason = None
    delta = MagicMock()
    delta.content = None

    tc = MagicMock()
    tc.index = index
    tc.id = call_id
    fn = MagicMock()
    fn.name = name
    fn.arguments = json.dumps(args)
    tc.function = fn
    delta.tool_calls = [tc]

    choice.delta = delta
    chunk.choices = [choice]
    return chunk


def _text_chunk(text: str):
    """Single streaming chunk carrying plain text content."""
    chunk = MagicMock()
    choice = MagicMock()
    choice.finish_reason = None
    delta = MagicMock()
    delta.content = text
    delta.tool_calls = None
    choice.delta = delta
    chunk.choices = [choice]
    return chunk


class _AsyncStream:
    """Async-iterable wrapper around a flat list of mock chunks."""

    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for chunk in self._chunks:
            yield chunk


def _make_agent(response_sequences):
    """
    Build an AgentService with:
    - mocked OpenAI client that returns response_sequences in order (one per API call)
    - mocked in-memory conversation_store
    """
    from app.services.agent import AgentService

    agent = AgentService.__new__(AgentService)
    agent.model = "gpt-4o-mini"

    cs = MagicMock()
    cs.get_messages.return_value = []
    cs.add_message = MagicMock()
    agent.conversation_store = cs

    streams = iter([_AsyncStream(chunks) for chunks in response_sequences])

    async def _create(**kwargs):
        return next(streams)

    client = MagicMock()
    client.chat.completions.create = _create
    agent.client = client

    return agent


async def _run(agent, execute_mock, question="add white silk shirt size M to cart"):
    """Collect all events from process_agent_stream with execute_tool + cart_service mocked."""
    events = []
    with patch("app.services.agent.execute_tool", execute_mock):
        with patch("app.services.cart.get_cart_service") as mock_cart_svc:
            mock_cart_svc.return_value.load_from_db = AsyncMock()
            async for event in agent.process_agent_stream(
                db=AsyncMock(),
                site_id="kasa",
                session_id="test-session",
                question=question,
                customer_id=uuid.uuid4(),
                brand_name="Kasa",
            ):
                events.append(event)
    return events


def _add_to_cart_args(product_id=PRODUCT_ID, size=SIZE, quantity=1):
    return {"product_id": product_id, "size": size, "quantity": quantity}


def _cart_result(product_id=PRODUCT_ID, quantity=1):
    return {"cart": {"items": [{"product_id": product_id, "size": SIZE, "quantity": quantity}], "item_count": quantity}}


# ---------------------------------------------------------------------------
# Core dedup test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_add_to_cart_within_turn_is_deduped():
    """
    When the LLM emits two parallel add_to_cart calls for the same product+size in
    one response, only the first dispatches add_to_cart; the second is substituted
    with get_cart (returning current cart state without re-adding).
    """
    execute_mock = AsyncMock(return_value=_cart_result())

    agent = _make_agent([
        # Iteration 1: two parallel add_to_cart for the same product+size
        [
            _tool_call_chunk(0, "tc-1", "add_to_cart", _add_to_cart_args()),
            _tool_call_chunk(1, "tc-2", "add_to_cart", _add_to_cart_args()),
        ],
        # Iteration 2: LLM produces a text reply after seeing tool results
        [_text_chunk("I've added the shirt to your cart!")],
    ])

    await _run(agent, execute_mock)

    calls = execute_mock.call_args_list
    assert len(calls) == 2, f"expected 2 execute_tool calls, got {len(calls)}"
    assert calls[0].kwargs["tool_name"] == "add_to_cart", "first call must be add_to_cart"
    assert calls[1].kwargs["tool_name"] == "get_cart", "second call must be substituted with get_cart"


@pytest.mark.asyncio
async def test_dedup_substitution_receives_correct_tool_call_id():
    """
    The tool result message appended to the conversation for the deduped call must
    use the second tool_call_id (tc-2), not the first — otherwise the OpenAI API
    would reject the next request with a mismatched tool_call_id error.
    """
    execute_mock = AsyncMock(return_value=_cart_result())

    agent = _make_agent([
        [
            _tool_call_chunk(0, "tc-first", "add_to_cart", _add_to_cart_args()),
            _tool_call_chunk(1, "tc-second", "add_to_cart", _add_to_cart_args()),
        ],
        [_text_chunk("Done!")],
    ])

    # Capture messages passed to the OpenAI client on the second call
    second_call_messages = None

    async def _create(**kwargs):
        nonlocal second_call_messages
        if second_call_messages is None:
            # First call: return tool-call chunks
            return _AsyncStream([
                _tool_call_chunk(0, "tc-first", "add_to_cart", _add_to_cart_args()),
                _tool_call_chunk(1, "tc-second", "add_to_cart", _add_to_cart_args()),
            ])
        else:
            return _AsyncStream([_text_chunk("Done!")])

    # Intercept the second API call to capture messages
    original_create = agent.client.chat.completions.create
    call_count = 0

    async def _patched_create(**kwargs):
        nonlocal call_count, second_call_messages
        call_count += 1
        if call_count == 2:
            second_call_messages = kwargs.get("messages", [])
        return await original_create(**kwargs)

    agent.client.chat.completions.create = _patched_create

    await _run(agent, execute_mock)

    # The messages fed into the second LLM call must include a tool result for tc-second
    tool_result_ids = [
        m["tool_call_id"]
        for m in (second_call_messages or [])
        if m.get("role") == "tool"
    ]
    assert "tc-second" in tool_result_ids, (
        f"deduped call's tool_call_id must be tc-second; tool result IDs found: {tool_result_ids}"
    )


# ---------------------------------------------------------------------------
# Per-turn scope guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dedup_is_per_turn_not_per_process():
    """
    cart_adds_this_turn is local to each process_agent_stream invocation.
    Adding the same product in two sequential turns must not trigger the dedup
    guard on the second turn — the set is freshly empty each call.
    """
    execute_mock = AsyncMock(return_value=_cart_result())

    # Same agent instance, two sequential turns
    agent = _make_agent([
        # Turn 1: single add_to_cart
        [_tool_call_chunk(0, "tc-a", "add_to_cart", _add_to_cart_args())],
        [_text_chunk("Added!")],
        # Turn 2: same product+size again — must NOT be deduped
        [_tool_call_chunk(0, "tc-b", "add_to_cart", _add_to_cart_args())],
        [_text_chunk("Added again!")],
    ])

    await _run(agent, execute_mock, question="add shirt size M")  # Turn 1
    await _run(agent, execute_mock, question="add shirt size M")  # Turn 2

    add_calls = [c for c in execute_mock.call_args_list if c.kwargs.get("tool_name") == "add_to_cart"]
    assert len(add_calls) == 2, (
        f"both turns must call add_to_cart independently; add_to_cart calls: {len(add_calls)}"
    )


# ---------------------------------------------------------------------------
# Differential dedup tests — dedup must NOT fire for distinct product/size pairs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_same_product_different_size_both_proceed():
    """
    Two add_to_cart calls for the same product_id but different sizes (M and L)
    must both execute — this is a legitimate 'add both sizes' scenario.
    """
    execute_mock = AsyncMock(return_value=_cart_result())

    agent = _make_agent([
        [
            _tool_call_chunk(0, "tc-1", "add_to_cart", _add_to_cart_args(size="M")),
            _tool_call_chunk(1, "tc-2", "add_to_cart", _add_to_cart_args(size="L")),
        ],
        [_text_chunk("Added both sizes!")],
    ])

    await _run(agent, execute_mock)

    add_calls = [c for c in execute_mock.call_args_list if c.kwargs.get("tool_name") == "add_to_cart"]
    assert len(add_calls) == 2, "different sizes must not be deduped"
    sizes = {c.kwargs["tool_args"]["size"] for c in add_calls}
    assert sizes == {"M", "L"}


@pytest.mark.asyncio
async def test_different_products_same_size_both_proceed():
    """
    Two add_to_cart calls for different product_ids with the same size must both
    execute — customer is adding two distinct products.
    """
    execute_mock = AsyncMock(return_value=_cart_result())

    agent = _make_agent([
        [
            _tool_call_chunk(0, "tc-1", "add_to_cart", _add_to_cart_args(product_id=PRODUCT_ID)),
            _tool_call_chunk(1, "tc-2", "add_to_cart", _add_to_cart_args(product_id=PRODUCT_ID_2)),
        ],
        [_text_chunk("Added both products!")],
    ])

    await _run(agent, execute_mock)

    add_calls = [c for c in execute_mock.call_args_list if c.kwargs.get("tool_name") == "add_to_cart"]
    assert len(add_calls) == 2, "different product_ids must not be deduped"
    pids = {c.kwargs["tool_args"]["product_id"] for c in add_calls}
    assert pids == {PRODUCT_ID, PRODUCT_ID_2}


@pytest.mark.asyncio
async def test_empty_product_id_deduped_on_second_call():
    """
    Two add_to_cart calls with empty product_id are treated as the same key and
    deduped — the second is replaced with get_cart. Documented behavior: this masks
    one of two error paths (_add_to_cart already returns 'Product not found' for
    empty IDs), but the net effect is identical to the user (error on first call).
    """
    execute_mock = AsyncMock(return_value={"cart": {"items": [], "item_count": 0}})

    agent = _make_agent([
        [
            _tool_call_chunk(0, "tc-1", "add_to_cart", {"product_id": "", "size": SIZE, "quantity": 1}),
            _tool_call_chunk(1, "tc-2", "add_to_cart", {"product_id": "", "size": SIZE, "quantity": 1}),
        ],
        [_text_chunk("I couldn't find that product.")],
    ])

    await _run(agent, execute_mock)

    calls = execute_mock.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["tool_name"] == "add_to_cart"
    assert calls[1].kwargs["tool_name"] == "get_cart"
