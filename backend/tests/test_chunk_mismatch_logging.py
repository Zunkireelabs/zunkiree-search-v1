"""
Vector orphans brief (2026-09-24, session 53), A4: CHUNK_MISMATCH used to
log only a count of the vector ids Postgres had no chunk for -- enough to
see a mismatch happened, not enough to diagnose *which* vectors were
orphaned. It now logs the missing ids too (capped at 50, so a pathological
namespace can't flood the logs).
"""
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.query as query_module
from app.services.query import QueryService


def _make_customer():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.website_type = "ecommerce"
    return customer


def _make_chunk(vector_id):
    chunk = MagicMock()
    chunk.vector_id = vector_id
    chunk.content = f"content for {vector_id}"
    chunk.source_url = ""
    chunk.source_title = "Source"
    return chunk


@pytest.mark.asyncio
async def test_chunk_mismatch_logs_the_missing_ids(caplog):
    service = QueryService()
    customer = _make_customer()

    # 8 vector ids come back from Pinecone/fusion; Postgres only has one of
    # them (matches the kasa-clothing prod incident shape: postgres_chunks
    # far short of vector_ids_requested).
    all_ids = [f"vec_{i}" for i in range(8)]
    found_chunk = _make_chunk(all_ids[0])

    service.embedding_service.create_embedding = AsyncMock(return_value=[0.1] * 8)
    service.vector_store.query_vectors = AsyncMock(
        return_value=[{"id": vid, "score": 0.5, "metadata": {}} for vid in all_ids]
    )
    service._keyword_search = AsyncMock(return_value=[])
    service._fetch_chunks_by_vector_ids = AsyncMock(return_value=[found_chunk])

    db = AsyncMock()

    with caplog.at_level(logging.WARNING, logger="zunkiree.query.service"):
        await service._retrieve_and_rank(
            db=db, customer=customer, config=None, site_id="kasa-clothing", question="t-shirts?"
        )

    mismatch_records = [r for r in caplog.records if "CHUNK_MISMATCH" in r.getMessage()]
    assert len(mismatch_records) == 1
    rendered = mismatch_records[0].getMessage()

    assert "missing_count=7" in rendered
    for vid in all_ids[1:]:
        assert vid in rendered
    # The one id that WAS found in Postgres must not be reported as missing.
    assert all_ids[0] not in rendered.split("missing_ids=")[1]


@pytest.mark.asyncio
async def test_chunk_mismatch_caps_logged_ids_at_50():
    # Real fusion caps fused_ids at adaptive_top_k (max 8), so a namespace
    # can't naturally produce more than ~8 missing ids through this call
    # chain today -- but the cap is defensive against that changing, so
    # exercise it directly by making fusion hand back more ids than that.
    service = QueryService()
    customer = _make_customer()

    all_ids = [f"vec_{i}" for i in range(60)]

    service.embedding_service.create_embedding = AsyncMock(return_value=[0.1] * 8)
    service.vector_store.query_vectors = AsyncMock(
        return_value=[{"id": all_ids[0], "score": 0.5, "metadata": {}}]
    )
    service._keyword_search = AsyncMock(return_value=[])
    service._fetch_chunks_by_vector_ids = AsyncMock(return_value=[])

    db = AsyncMock()

    logged = {}

    class _CapturingHandler(logging.Handler):
        def emit(self, record):
            if "CHUNK_MISMATCH" in record.getMessage():
                logged["message"] = record.getMessage()

    logger = logging.getLogger("zunkiree.query.service")
    handler = _CapturingHandler()
    logger.addHandler(handler)
    try:
        with patch.object(query_module, "_reciprocal_rank_fusion", return_value=all_ids):
            await service._retrieve_and_rank(
                db=db, customer=customer, config=None, site_id="kasa-clothing", question="anything"
            )
    finally:
        logger.removeHandler(handler)

    assert "missing_count=60" in logged["message"]
    # Only the first 50 ids were rendered into the log line even though 60
    # were missing.
    assert logged["message"].count("vec_") == 50
