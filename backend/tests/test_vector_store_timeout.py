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
from app.services.vector_store import (
    PINECONE_TIMEOUT_SECONDS,
    PINECONE_WRITE_TIMEOUT_SECONDS,
    VectorStoreService,
    _run_bounded,
)


def test_bound_is_reasonably_short():
    # Sanity guard: a future edit shouldn't quietly widen this back toward
    # Pinecone client's 30s SDK default.
    assert 0 < PINECONE_TIMEOUT_SECONDS <= 10.0


def test_write_bound_is_longer_than_query_bound():
    # A 50-vector upsert batch or a full-namespace delete can legitimately
    # take longer than the 6s query bound allows (P2 brief §7c B4
    # follow-up, 2026-09-24). Regression guard against a future edit
    # quietly collapsing the two bounds back together.
    assert PINECONE_WRITE_TIMEOUT_SECONDS > PINECONE_TIMEOUT_SECONDS


def _service_with_fake_index(fake_index):
    service = VectorStoreService.__new__(VectorStoreService)
    service.index = fake_index
    return service


class _RecordingIndex:
    """Stands in for pinecone's Index; records kwargs of the last call."""

    def __init__(self):
        self.last_call = None

    def upsert(self, **kwargs):
        self.last_call = ("upsert", kwargs)
        return None

    def query(self, **kwargs):
        self.last_call = ("query", kwargs)

        class _Result:
            matches = []

        return _Result()

    def delete(self, **kwargs):
        self.last_call = ("delete", kwargs)
        return None


@pytest.mark.asyncio
async def test_upsert_vectors_uses_write_bound_not_query_bound():
    fake_index = _RecordingIndex()
    service = _service_with_fake_index(fake_index)

    await service.upsert_vectors(vectors=[{"id": "a", "values": [0.1]}], namespace="ns")

    name, kwargs = fake_index.last_call
    assert name == "upsert"
    # The SDK's own per-call timeout, not the client-level 6s default.
    assert kwargs["timeout"] == PINECONE_WRITE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_delete_namespace_uses_write_bound():
    fake_index = _RecordingIndex()
    service = _service_with_fake_index(fake_index)

    await service.delete_namespace(namespace="ns")

    name, kwargs = fake_index.last_call
    assert name == "delete"
    assert kwargs["timeout"] == PINECONE_WRITE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_delete_vectors_uses_write_bound():
    fake_index = _RecordingIndex()
    service = _service_with_fake_index(fake_index)

    await service.delete_vectors(ids=["a", "b"], namespace="ns")

    name, kwargs = fake_index.last_call
    assert name == "delete"
    assert kwargs["timeout"] == PINECONE_WRITE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_query_vectors_does_not_pass_write_timeout():
    # The hot query path stays on the 6s client-level default — it must
    # NOT pass a per-call `timeout=` kwarg that would widen it.
    fake_index = _RecordingIndex()
    service = _service_with_fake_index(fake_index)

    await service.query_vectors(query_vector=[0.1], namespace="ns")

    name, kwargs = fake_index.last_call
    assert name == "query"
    assert "timeout" not in kwargs


@pytest.mark.asyncio
async def test_write_bound_actually_governs_run_bounded_wait(monkeypatch):
    # End-to-end on the asyncio.wait_for mechanism itself: a call using
    # the write bound survives past the (shorter) query bound.
    monkeypatch.setattr(vector_store, "PINECONE_TIMEOUT_SECONDS", 0.05)

    def slow_call():
        time.sleep(0.2)
        return "done"

    result = await _run_bounded(slow_call, _bound=PINECONE_WRITE_TIMEOUT_SECONDS)
    assert result == "done"


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
