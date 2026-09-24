"""
Vector orphans brief (2026-09-24, session 53), A1: `_process_chunks` used to
upsert to Pinecone *before* committing the matching `DocumentChunk` rows. A
failure/timeout between those two calls left a live Pinecone vector with no
Postgres row behind it, forever -- the root cause of kasa-clothing's
CHUNK_MISMATCH `<job_id>_<i>`-shaped orphans. The fix commits the Postgres
rows first, then upserts, so a failed upsert leaves a row with no vector
(harmless -- keyword search still finds it) instead of the reverse.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ingestion import IngestionService


def _make_job():
    job = MagicMock()
    job.id = uuid.uuid4()
    job.customer_id = uuid.uuid4()
    return job


def _make_chunks(n=2):
    return [
        {
            "content": f"chunk {i}",
            "chunk_index": i,
            "source_url": "https://example.com",
            "source_title": "Example",
            "token_count": 10,
        }
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_postgres_commit_happens_before_pinecone_upsert():
    service = IngestionService()
    job = _make_job()

    db = AsyncMock()
    call_order = []
    db.commit.side_effect = lambda: call_order.append("db.commit")
    db.add = MagicMock()  # sync method on AsyncSession

    service.embedding_service.create_embeddings = AsyncMock(
        return_value=[[0.1, 0.2], [0.3, 0.4]]
    )

    async def recording_upsert(vectors, namespace):
        call_order.append("pinecone.upsert")
        return len(vectors)

    service.vector_store.upsert_vectors = recording_upsert

    await service._process_chunks(db=db, job=job, site_id="kasa-clothing", chunks=_make_chunks())

    # The Postgres commit (persisting the DocumentChunk rows) must happen
    # before the Pinecone upsert, not after.
    assert call_order[0] == "db.commit"
    assert call_order[1] == "pinecone.upsert"


@pytest.mark.asyncio
async def test_document_chunk_rows_are_committed_even_if_pinecone_upsert_fails():
    # A failed/timed-out Pinecone upsert must not roll back or prevent the
    # already-committed DocumentChunk rows -- a row without a vector is the
    # safe direction (keyword search still finds it; a vector without a row
    # is the bug this fix closes).
    service = IngestionService()
    job = _make_job()

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    service.embedding_service.create_embeddings = AsyncMock(
        return_value=[[0.1, 0.2], [0.3, 0.4]]
    )
    service.vector_store.upsert_vectors = AsyncMock(side_effect=TimeoutError("pinecone stalled"))

    with pytest.raises(TimeoutError):
        await service._process_chunks(db=db, job=job, site_id="kasa-clothing", chunks=_make_chunks())

    # The commit that persists the DocumentChunk rows already happened
    # before the upsert raised.
    assert db.commit.await_count >= 1
    assert db.add.call_count == 2  # both chunks were added to the session
