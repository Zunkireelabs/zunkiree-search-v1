import time
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Customer, WidgetConfig, Domain, QueryLog
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service
from app.services.llm import get_llm_service
from app.config import get_settings

settings = get_settings()


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

        Args:
            db: Database session
            site_id: Customer's site ID
            question: User's question
            origin: Request origin domain
            user_agent: User agent string
            ip_address: Client IP address

        Returns:
            Dict with answer, suggestions, and sources
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

        # Retrieve relevant chunks
        chunks = await self.vector_store.query_vectors(
            query_vector=query_embedding,
            namespace=site_id,
            top_k=settings.top_k_chunks,
        )

        # Generate answer
        result = await self.llm_service.generate_answer(
            question=question,
            context_chunks=chunks,
            brand_name=config.brand_name if config else customer.name,
            tone=config.tone if config else "neutral",
            fallback_message=config.fallback_message if config else "I don't have that information yet.",
            max_tokens=config.max_response_length if config else 500,
        )

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Log query
        await self._log_query(
            db=db,
            customer_id=customer.id,
            question=question,
            answer=result["answer"],
            chunks_used=len(chunks),
            response_time_ms=response_time_ms,
            origin=origin,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        # Build sources from chunks
        sources = []
        seen_urls = set()
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            url = metadata.get("source_url")
            title = metadata.get("source_title", "Source")
            if url and url not in seen_urls:
                sources.append({"title": title, "url": url})
                seen_urls.add(url)

        return {
            "answer": result["answer"],
            "suggestions": result["suggestions"] if config and config.show_suggestions else [],
            "sources": sources if config and config.show_sources else [],
        }

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
