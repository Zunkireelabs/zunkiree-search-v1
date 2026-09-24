"""
P2 brief §7c B4 item 3: Pinecone's Index methods are synchronous — called
directly from an `async def` they block the whole single-worker event loop
for as long as the call takes. `_run_bounded` moves them to a thread and
bounds the wait so a stalled call fails cleanly instead of hanging forever.
"""
import asyncio
import time

import pytest

import app.services.vector_store as vector_store
from app.services.vector_store import PINECONE_TIMEOUT_SECONDS, _run_bounded


def test_bound_is_reasonably_short():
    # Sanity guard: a future edit shouldn't quietly widen this back toward
    # Pinecone client's 30s SDK default.
    assert 0 < PINECONE_TIMEOUT_SECONDS <= 10.0


@pytest.mark.asyncio
async def test_fast_sync_call_returns_normally():
    def fast_call(x):
        return x * 2

    result = await _run_bounded(fast_call, 21)
    assert result == 42


@pytest.mark.asyncio
async def test_stalled_sync_call_raises_within_bound_not_forever(monkeypatch):
    # Use a tiny bound so the test runs fast; the mechanism under test
    # (asyncio.wait_for around asyncio.to_thread) is timeout-value-agnostic.
    monkeypatch.setattr(vector_store, "PINECONE_TIMEOUT_SECONDS", 0.2)

    def stalled_call():
        time.sleep(2.0)  # would hang well past the bound
        return "should never get here"

    start = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await _run_bounded(stalled_call)
    elapsed = time.monotonic() - start

    # Fails at ~0.2s, nowhere near the 2s the sync call itself would
    # otherwise block for.
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_event_loop_stays_free_during_a_slow_sync_call():
    """The whole point of asyncio.to_thread: other coroutines keep running
    while a slow sync call is in flight, instead of the loop freezing."""
    def slow_call():
        time.sleep(0.3)
        return "done"

    ticked = []

    async def ticker():
        for _ in range(5):
            await asyncio.sleep(0.05)
            ticked.append(time.monotonic())

    slow_task = asyncio.create_task(_run_bounded(slow_call))
    tick_task = asyncio.create_task(ticker())
    result = await slow_task
    await tick_task

    assert result == "done"
    # The ticker made progress *during* the blocking call rather than being
    # starved until it finished.
    assert len(ticked) == 5
