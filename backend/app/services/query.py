import time
import hashlib
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models import Customer, WidgetConfig, Domain, QueryLog, DocumentChunk
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service
from app.services.llm import get_llm_service
from app.utils.chunking import count_tokens
from app.config import get_settings

logger = logging.getLogger("zunkiree.query.service")

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

        # [TEMP-LOG] Log Pinecone query params
        logger.warning("[QUERY-TRACE] pinecone_namespace=%s site_id_filter=%s top_k=%s embedding_dim=%d", site_id, site_id, settings.top_k_chunks, len(query_embedding))

        # --- Hybrid retrieval: vector + keyword ---

        # List A: Pinecone vector search
        vector_matches = await self.vector_store.query_vectors(
            query_vector=query_embedding,
            namespace=site_id,
            top_k=settings.top_k_chunks,
            site_id=site_id,
        )
        vector_ids = [match["id"] for match in vector_matches]
        logger.warning("[QUERY-TRACE] vector_results_ids=%s", vector_ids[:5])

        # List B: Postgres full-text keyword search
        keyword_ids = await self._keyword_search(db, customer.id, question, limit=settings.top_k_chunks)
        logger.warning("[QUERY-TRACE] keyword_results_ids=%s", keyword_ids[:5])

        # Fuse results via Reciprocal Rank Fusion
        fused_ids = _reciprocal_rank_fusion(vector_ids, keyword_ids, k=60, top_n=settings.top_k_chunks)
        logger.warning("[QUERY-TRACE] fused_results_ids=%s", fused_ids[:5])

        # No-data detection: if both searches returned 0 results, return fallback
        if not fused_ids:
            fallback = config.fallback_message if config else "I don't have that information yet."
            logger.warning("[QUERY-TRACE] FALLBACK_TRIGGERED reason=zero_fused_matches site_id=%s", site_id)
            return {
                "answer": fallback,
                "suggestions": [],
                "sources": [],
            }

        # Fetch full chunk content from PostgreSQL (defense-in-depth: filter by customer_id)
        db_chunks = await self._fetch_chunks_by_vector_ids(db, fused_ids, customer.id)

        # [TEMP-LOG] Log Postgres chunk fetch results
        logger.warning("[QUERY-TRACE] postgres_chunks=%d customer_id=%s vector_ids_requested=%d", len(db_chunks), customer.id, len(fused_ids))
        if len(db_chunks) < len(fused_ids):
            logger.warning("[QUERY-TRACE] CHUNK_MISMATCH missing_count=%d", len(fused_ids) - len(db_chunks))

        # Build ordered chunk list preserving RRF fusion ranking
        fused_rank = {vid: idx for idx, vid in enumerate(fused_ids)}
        chunks_for_llm = []
        for chunk in db_chunks:
            chunks_for_llm.append({
                "content": chunk.content,
                "source_url": chunk.source_url or "",
                "source_title": chunk.source_title or "Source",
                "score": len(fused_ids) - fused_rank.get(chunk.vector_id, len(fused_ids)),
            })

        # Sort by fusion rank (highest score = best rank)
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

    async def _keyword_search(
        self,
        db: AsyncSession,
        customer_id,
        question: str,
        limit: int = 5,
    ) -> list[str]:
        """
        Full-text keyword search on document_chunks.
        Returns ranked list of vector_ids.
        """
        result = await db.execute(
            text("""
                SELECT vector_id,
                       ts_rank(search_vector, plainto_tsquery('english', :query)) AS rank
                FROM document_chunks
                WHERE customer_id = :customer_id
                  AND search_vector @@ plainto_tsquery('english', :query)
                ORDER BY rank DESC
                LIMIT :limit
            """),
            {"query": question, "customer_id": str(customer_id), "limit": limit},
        )
        return [row[0] for row in result.fetchall()]

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


def _reciprocal_rank_fusion(
    list_a: list[str],
    list_b: list[str],
    k: int = 60,
    top_n: int = 5,
) -> list[str]:
    """
    Reciprocal Rank Fusion of two ranked ID lists.
    Score per ID = sum of 1/(k + rank) across lists where it appears.
    """
    scores: dict[str, float] = {}
    for rank, vid in enumerate(list_a):
        scores[vid] = scores.get(vid, 0) + 1.0 / (k + rank)
    for rank, vid in enumerate(list_b):
        scores[vid] = scores.get(vid, 0) + 1.0 / (k + rank)
    sorted_ids = sorted(scores, key=scores.get, reverse=True)
    return sorted_ids[:top_n]


# Singleton instance
_query_service: QueryService | None = None


def get_query_service() -> QueryService:
    global _query_service
    if _query_service is None:
        _query_service = QueryService()
    return _query_service
