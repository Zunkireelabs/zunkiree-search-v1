from __future__ import annotations
from app.config import get_settings
from app.services.openai_client import get_openai_client

settings = get_settings()


class EmbeddingService:
    def __init__(self, kind: str = "embeddings"):
        self.client = get_openai_client(kind)
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions

    async def create_embedding(self, text: str) -> list[float]:
        """Create embedding for a single text."""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
        )
        return response.data[0].embedding

    async def create_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Create embeddings for multiple texts."""
        if not texts:
            return []

        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )
        return [item.embedding for item in response.data]


# Singleton instance — bound to the "embeddings" profile (8s timeout, 1
# retry). Used by the hot RAG retrieval path, which is voice-budgeted.
_embedding_service: EmbeddingService | None = None

# Singleton instance for background/bulk work — bound to the "background"
# profile (120s timeout, 2 retries) so a single-item ingest or an inbound
# webhook's per-row embed doesn't fail outright on a slow OpenAI call.
_background_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def get_background_embedding_service() -> EmbeddingService:
    global _background_embedding_service
    if _background_embedding_service is None:
        _background_embedding_service = EmbeddingService(kind="background")
    return _background_embedding_service
