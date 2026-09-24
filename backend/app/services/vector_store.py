from __future__ import annotations
import asyncio
import logging
from pinecone import Pinecone
from app.config import get_settings

logger = logging.getLogger("zunkiree.vector_store")
settings = get_settings()

# The Pinecone SDK's Index methods are synchronous (blocking) HTTP calls.
# Called directly from an `async def`, a slow Pinecone response freezes the
# *entire* single-worker event loop (not just the one request) for as long
# as it takes — matching the "container idle, not looping" symptom in the
# P2 brief §7c B4 stage hang. Every call below runs in a thread via
# asyncio.to_thread (so the loop stays free) and under asyncio.wait_for (so
# a stalled call still fails within a bound instead of pinning a thread-pool
# slot indefinitely).
#
# Two bounds:
# - PINECONE_TIMEOUT_SECONDS (6s): the hot query path (query_vectors), which
#   sits in a voice-budgeted /query/stream turn — same rationale as before.
# - PINECONE_WRITE_TIMEOUT_SECONDS (60s): upsert_vectors and
#   delete_namespace/delete_vectors, called from ingestion and the inbound
#   dispatcher, neither of which is voice-budgeted. A 50-vector upsert batch
#   or a full-namespace delete can legitimately take longer than the 6s
#   query bound allows, and failing an ingest/dispatcher write outright is
#   worse than it taking longer (P2 brief §7c B4 follow-up, 2026-09-24).
#   Passed as a per-call `timeout=` kwarg (upsert/delete both support one,
#   overriding the client-level default) rather than raising the client's
#   own wire-level timeout, so the hot query path's wire-level bound stays
#   at 6s.
PINECONE_TIMEOUT_SECONDS = 6.0
PINECONE_WRITE_TIMEOUT_SECONDS = 60.0


async def _run_bounded(fn, *args, _bound: float | None = None, **kwargs):
    """Run `fn` in a thread under an asyncio.wait_for bound.

    `_bound` is this wrapper's own asyncio-level deadline (leading
    underscore so it can't collide with a `timeout` kwarg meant for `fn`
    itself, e.g. the SDK's own per-call `timeout=` on upsert/delete — every
    other kwarg passes straight through to `fn`). Defaults to
    PINECONE_TIMEOUT_SECONDS, read from module scope at call time (not as
    a function-default) so monkeypatching that module attribute still
    takes effect for callers that don't pass `_bound` explicitly.
    """
    if _bound is None:
        _bound = PINECONE_TIMEOUT_SECONDS
    return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), timeout=_bound)


class VectorStoreService:
    def __init__(self):
        # Also tighten the client's own wire-level timeout (default 30s) so
        # the underlying HTTP call is bounded even independent of the
        # to_thread wrapper above.
        self.pc = Pinecone(api_key=settings.pinecone_api_key, timeout=PINECONE_TIMEOUT_SECONDS)
        self.index = self.pc.Index(
            name=settings.pinecone_index_name,
            host=settings.pinecone_host,
        )

    async def upsert_vectors(
        self,
        vectors: list[dict],
        namespace: str,
    ) -> int:
        """
        Upsert vectors to Pinecone.

        Args:
            vectors: List of dicts with 'id', 'values', and optional 'metadata'
            namespace: Customer namespace (site_id)

        Returns:
            Number of vectors upserted
        """
        if not vectors:
            return 0

        # Batch upserts to stay under Pinecone's 4MB request limit.
        # With 3072-dim embeddings (~12KB per vector), 50 vectors ≈ 600KB.
        batch_size = 50
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            await _run_bounded(
                self.index.upsert,
                vectors=batch,
                namespace=namespace,
                timeout=PINECONE_WRITE_TIMEOUT_SECONDS,
                _bound=PINECONE_WRITE_TIMEOUT_SECONDS,
            )
        return len(vectors)

    async def query_vectors(
        self,
        query_vector: list[float],
        namespace: str,
        top_k: int = 5,
        site_id: str | None = None,
        filter_metadata: dict | None = None,
    ) -> list[dict]:
        """
        Query vectors from Pinecone. Returns vector IDs and scores only.
        Full content is fetched from PostgreSQL by the query service.

        Args:
            query_vector: The query embedding
            namespace: Customer namespace (site_id)
            top_k: Number of results to return
            site_id: Optional site_id for metadata filter (defense-in-depth)
            filter_metadata: Optional additional metadata filter (e.g. {"type": "product"})

        Returns:
            List of matches with IDs, scores, and metadata
        """
        # Defense-in-depth: metadata filter even though namespace already isolates
        query_filter = {}
        if site_id:
            query_filter["site_id"] = {"$eq": site_id}
        if filter_metadata:
            for key, value in filter_metadata.items():
                query_filter[key] = {"$eq": value} if not isinstance(value, dict) else value

        if not query_filter:
            query_filter = None

        include_metadata = bool(filter_metadata)

        # [TEMP-LOG] Log Pinecone query details
        logger.warning("[QUERY-TRACE] pinecone_query namespace=%s top_k=%d filter=%s index=%s", namespace, top_k, query_filter, settings.pinecone_index_name)

        results = await _run_bounded(
            self.index.query,
            vector=query_vector,
            namespace=namespace,
            top_k=top_k,
            include_metadata=include_metadata,
            filter=query_filter,
        )

        # [TEMP-LOG] Log raw Pinecone response
        logger.warning("[QUERY-TRACE] pinecone_raw_matches=%d scores=%s", len(results.matches), [(m.id[:20], m.score) for m in results.matches[:5]])

        return [
            {
                "id": match.id,
                "score": match.score,
                "metadata": dict(match.metadata) if hasattr(match, 'metadata') and match.metadata else {},
            }
            for match in results.matches
        ]

    async def delete_namespace(self, namespace: str) -> None:
        """Delete all vectors in a namespace."""
        await _run_bounded(
            self.index.delete,
            delete_all=True,
            namespace=namespace,
            timeout=PINECONE_WRITE_TIMEOUT_SECONDS,
            _bound=PINECONE_WRITE_TIMEOUT_SECONDS,
        )

    async def delete_vectors(self, ids: list[str], namespace: str) -> None:
        """Delete specific vectors by ID."""
        if ids:
            await _run_bounded(
                self.index.delete,
                ids=ids,
                namespace=namespace,
                timeout=PINECONE_WRITE_TIMEOUT_SECONDS,
                _bound=PINECONE_WRITE_TIMEOUT_SECONDS,
            )


# Singleton instance
_vector_store_service: VectorStoreService | None = None


def get_vector_store_service() -> VectorStoreService:
    global _vector_store_service
    if _vector_store_service is None:
        _vector_store_service = VectorStoreService()
    return _vector_store_service
