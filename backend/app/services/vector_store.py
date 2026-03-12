import logging
from pinecone import Pinecone
from app.config import get_settings

logger = logging.getLogger("zunkiree.vector_store")
settings = get_settings()


class VectorStoreService:
    def __init__(self):
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
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
            self.index.upsert(
                vectors=batch,
                namespace=namespace,
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

        results = self.index.query(
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
        self.index.delete(delete_all=True, namespace=namespace)

    async def delete_vectors(self, ids: list[str], namespace: str) -> None:
        """Delete specific vectors by ID."""
        if ids:
            self.index.delete(ids=ids, namespace=namespace)


# Singleton instance
_vector_store_service: VectorStoreService | None = None


def get_vector_store_service() -> VectorStoreService:
    global _vector_store_service
    if _vector_store_service is None:
        _vector_store_service = VectorStoreService()
    return _vector_store_service
