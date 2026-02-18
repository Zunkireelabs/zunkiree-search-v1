from pinecone import Pinecone
from app.config import get_settings

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

        # Pinecone upsert is synchronous, but we wrap it
        self.index.upsert(
            vectors=vectors,
            namespace=namespace,
        )
        return len(vectors)

    async def query_vectors(
        self,
        query_vector: list[float],
        namespace: str,
        top_k: int = 5,
        site_id: str | None = None,
    ) -> list[dict]:
        """
        Query vectors from Pinecone. Returns vector IDs and scores only.
        Full content is fetched from PostgreSQL by the query service.

        Args:
            query_vector: The query embedding
            namespace: Customer namespace (site_id)
            top_k: Number of results to return
            site_id: Optional site_id for metadata filter (defense-in-depth)

        Returns:
            List of matches with IDs and scores
        """
        # Defense-in-depth: metadata filter even though namespace already isolates
        query_filter = None
        if site_id:
            query_filter = {"site_id": {"$eq": site_id}}

        results = self.index.query(
            vector=query_vector,
            namespace=namespace,
            top_k=top_k,
            include_metadata=False,
            filter=query_filter,
        )

        return [
            {
                "id": match.id,
                "score": match.score,
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
