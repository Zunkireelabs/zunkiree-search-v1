import time
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Customer, WidgetConfig, Domain, QueryLog, DocumentChunk
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service
from app.services.llm import get_llm_service
from app.utils.chunking import count_tokens
from app.config import get_settings

settings = get_settings()

# Maximum tokens of context to feed the LLM (prevents exceeding model limits)
MAX_CONTEXT_TOKENS = 4000


class QueryService:
    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store_service()
        self.llm_service = get_llm_service()

    async def process_query(
        self,
        db: AsyncSession,
        site_id: str,
        question: str,
        origin: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> dict:
        """
        Process a user query end-to-end.

        Flow:
        1. Validate customer + origin
        2. Embed question via OpenAI
        3. Retrieve top-k vector IDs from Pinecone (namespace = site_id)
        4. Fetch full chunk content from PostgreSQL (filtered by customer_id)
        5. Assemble token-capped context
        6. Generate answer via LLM
        7. Log query
        """
        start_time = time.time()

        # Get customer and validate
        customer = await self._get_customer(db, site_id)
        if not customer:
            raise ValueError("Invalid site_id")

        # Validate origin domain
        if origin and not await self._validate_origin(db, customer.id, origin):
            raise PermissionError("Origin domain not allowed")

        # Get widget config
        config = await self._get_widget_config(db, customer.id)

        # Generate query embedding
        query_embedding = await self.embedding_service.create_embedding(question)

        # Retrieve relevant vector IDs from Pinecone (scores only, no metadata)
        vector_matches = await self.vector_store.query_vectors(
            query_vector=query_embedding,
            namespace=site_id,
            top_k=settings.top_k_chunks,
            site_id=site_id,
        )

        # Extract vector IDs
        vector_ids = [match["id"] for match in vector_matches]

        # No-data detection: if Pinecone returned 0 results, return fallback immediately
        if not vector_ids:
            fallback = config.fallback_message if config else "I don't have that information yet."
            return {
                "answer": fallback,
                "suggestions": [],
                "sources": [],
            }

        # Fetch full chunk content from PostgreSQL (defense-in-depth: filter by customer_id)
        db_chunks = await self._fetch_chunks_by_vector_ids(db, vector_ids, customer.id)

        # Build ordered chunk list preserving Pinecone relevance ranking
        vector_id_to_score = {match["id"]: match["score"] for match in vector_matches}
        chunks_for_llm = []
        for chunk in db_chunks:
            chunks_for_llm.append({
                "content": chunk.content,
                "source_url": chunk.source_url or "",
                "source_title": chunk.source_title or "Source",
                "score": vector_id_to_score.get(chunk.vector_id, 0),
            })

        # Sort by Pinecone relevance score (highest first)
        chunks_for_llm.sort(key=lambda c: c["score"], reverse=True)

        # Determine if suggestions should be generated
        show_suggestions = config.show_suggestions if config else True

        # Generate answer with token-capped context
        result = await self.llm_service.generate_answer(
            question=question,
            context_chunks=chunks_for_llm,
            brand_name=config.brand_name if config else customer.name,
            tone=config.tone if config else "neutral",
            fallback_message=config.fallback_message if config else "I don't have that information yet.",
            max_tokens=config.max_response_length if config else 500,
            show_suggestions=show_suggestions,
        )

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Log query
        await self._log_query(
            db=db,
            customer_id=customer.id,
            question=question,
            answer=result["answer"],
            chunks_used=len(chunks_for_llm),
            response_time_ms=response_time_ms,
            origin=origin,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        # Build deduplicated sources list
        sources = []
        seen_urls = set()
        for chunk in chunks_for_llm:
            url = chunk["source_url"]
            title = chunk["source_title"]
            if url and url not in seen_urls:
                sources.append({"title": title, "url": url})
                seen_urls.add(url)

        return {
            "answer": result["answer"],
            "suggestions": result["suggestions"] if show_suggestions else [],
            "sources": sources if config and config.show_sources else [],
        }

    async def _fetch_chunks_by_vector_ids(
        self,
        db: AsyncSession,
        vector_ids: list[str],
        customer_id,
    ) -> list[DocumentChunk]:
        """
        Fetch full chunk content from PostgreSQL by vector IDs.
        Defense-in-depth: always filter by customer_id to prevent cross-tenant leakage.
        """
        if not vector_ids:
            return []

        result = await db.execute(
            select(DocumentChunk).where(
                DocumentChunk.vector_id.in_(vector_ids),
                DocumentChunk.customer_id == customer_id,
            )
        )
        return list(result.scalars().all())

    async def _get_customer(self, db: AsyncSession, site_id: str) -> Customer | None:
        """Get customer by site_id."""
        result = await db.execute(
            select(Customer).where(
                Customer.site_id == site_id,
                Customer.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def _get_widget_config(self, db: AsyncSession, customer_id) -> WidgetConfig | None:
        """Get widget config for customer."""
        result = await db.execute(
            select(WidgetConfig).where(WidgetConfig.customer_id == customer_id)
        )
        return result.scalar_one_or_none()

    async def _validate_origin(self, db: AsyncSession, customer_id, origin: str) -> bool:
        """Validate that origin domain is allowed for customer."""
        # Extract domain from origin
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            domain = parsed.netloc.lower()
            # Remove port if present
            domain = domain.split(":")[0]
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            return False

        # Check if domain is allowed
        result = await db.execute(
            select(Domain).where(
                Domain.customer_id == customer_id,
                Domain.is_active == True,
            )
        )
        allowed_domains = result.scalars().all()

        for allowed in allowed_domains:
            allowed_domain = allowed.domain.lower()
            if allowed_domain.startswith("www."):
                allowed_domain = allowed_domain[4:]
            if domain == allowed_domain or domain == f"www.{allowed_domain}":
                return True

        # Also allow localhost for development
        if domain in ["localhost", "127.0.0.1"]:
            return True

        return False

    async def _log_query(
        self,
        db: AsyncSession,
        customer_id,
        question: str,
        answer: str,
        chunks_used: int,
        response_time_ms: int,
        origin: str | None,
        user_agent: str | None,
        ip_address: str | None,
    ) -> None:
        """Log query to database."""
        ip_hash = None
        if ip_address:
            ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:64]

        log = QueryLog(
            customer_id=customer_id,
            question=question,
            answer=answer,
            chunks_used=chunks_used,
            response_time_ms=response_time_ms,
            origin_domain=origin,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )
        db.add(log)
        await db.commit()


# Singleton instance
_query_service: QueryService | None = None


def get_query_service() -> QueryService:
    global _query_service
    if _query_service is None:
        _query_service = QueryService()
    return _query_service
