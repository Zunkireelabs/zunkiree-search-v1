import time
import hashlib
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models import Customer, WidgetConfig, Domain, QueryLog, DocumentChunk, IngestionJob
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

    async def _check_ingestion_status(self, db: AsyncSession, customer_id) -> str:
        """
        Check ingestion status for a customer.
        Returns: "ready" | "processing" | "empty"
        """
        from sqlalchemy import func, case
        result = await db.execute(
            select(
                func.count().label("total"),
                func.sum(case((IngestionJob.status == "completed", 1), else_=0)).label("completed"),
                func.sum(case((IngestionJob.status == "processing", 1), else_=0)).label("processing"),
            ).where(IngestionJob.customer_id == customer_id)
        )
        row = result.one()
        total = row.total or 0
        completed = int(row.completed or 0)
        processing = int(row.processing or 0)

        if total == 0:
            return "empty"
        if completed > 0:
            return "ready"
        if processing > 0:
            return "processing"
        return "empty"

    async def process_query(
        self,
        db: AsyncSession,
        site_id: str,
        question: str,
        origin: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
        user_email: str | None = None,
        user_profile: dict | None = None,
        language: str | None = None,
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

        # --- Hybrid retrieval: vector + keyword ---
        # Phase 4A: Fetch wider candidate set (8) for adaptive top_k and potential reranking
        initial_fetch_k = 8

        # [TEMP-LOG] Log Pinecone query params
        logger.warning("[QUERY-TRACE] pinecone_namespace=%s site_id_filter=%s initial_fetch_k=%s embedding_dim=%d", site_id, site_id, initial_fetch_k, len(query_embedding))

        # List A: Pinecone vector search (wide fetch for adaptive layer)
        vector_matches = await self.vector_store.query_vectors(
            query_vector=query_embedding,
            namespace=site_id,
            top_k=initial_fetch_k,
            site_id=site_id,
        )
        vector_ids = [match["id"] for match in vector_matches]
        logger.warning("[QUERY-TRACE] vector_results_ids=%s", vector_ids[:5])

        # Compute retrieval score metrics from Pinecone results
        vector_scores = [match["score"] for match in vector_matches]
        top_score = max(vector_scores) if vector_scores else None
        avg_score = sum(vector_scores) / len(vector_scores) if vector_scores else None

        # --- Confidence threshold guard: skip LLM if top_score too low ---
        threshold = (
            config.confidence_threshold
            if config and config.confidence_threshold is not None
            else settings.confidence_threshold
        )

        if top_score is not None and top_score < threshold:
            logger.info(
                "[CONFIDENCE-GUARD] site_id=%s top_score=%.3f threshold=%.2f allowing_llm_general_knowledge=True",
                site_id, top_score, threshold,
            )

        # --- Phase 4A: Adaptive top_k and reranking decisions ---
        if top_score is not None and top_score > 0.6:
            adaptive_top_k = 3
        elif top_score is not None and top_score >= 0.4:
            adaptive_top_k = 5
        else:
            adaptive_top_k = 8

        # Reranking triggers only in the ambiguous zone
        rerank_needed = (
            top_score is not None
            and top_score > threshold
            and top_score < 0.45
        )

        # If reranking, fuse to 8 candidates first; otherwise fuse to adaptive_top_k
        fusion_top_n = 8 if rerank_needed else adaptive_top_k

        logger.info(
            "[ADAPTIVE] site_id=%s top_score=%.3f adaptive_top_k=%d rerank_needed=%s fusion_top_n=%d",
            site_id, top_score or 0, adaptive_top_k, rerank_needed, fusion_top_n,
        )

        # List B: Postgres full-text keyword search (boost with email if verified)
        keyword_query = f"{question} {user_email}" if user_email else question
        keyword_ids = await self._keyword_search(db, customer.id, keyword_query, limit=initial_fetch_k)
        logger.warning("[QUERY-TRACE] keyword_results_ids=%s", keyword_ids[:5])

        # Fuse results via Reciprocal Rank Fusion
        fused_ids = _reciprocal_rank_fusion(vector_ids, keyword_ids, k=60, top_n=fusion_top_n)
        logger.warning("[QUERY-TRACE] fused_results_ids=%s", fused_ids[:5])

        # No-data detection: check ingestion status for helpful messages
        if not fused_ids:
            status = await self._check_ingestion_status(db, customer.id)
            if status == "processing":
                return {
                    "answer": "I'm still learning about this website. Content is being indexed — please check back in a few minutes!",
                    "suggestions": [],
                    "sources": [],
                }
            elif status == "empty":
                return {
                    "answer": "I'm still setting up and don't have information about this website yet. Please check back soon!",
                    "suggestions": [],
                    "sources": [],
                }
            logger.info("[QUERY-TRACE] No fused matches, LLM will attempt general knowledge answer site_id=%s", site_id)

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

        # --- Phase 4A: Adaptive reranking for ambiguous queries ---
        rerank_triggered = False
        if rerank_needed and len(chunks_for_llm) > 1:
            chunks_for_llm = await self.llm_service.rerank_chunks(
                question=question,
                chunks=chunks_for_llm,
                top_n=5,
            )
            rerank_triggered = True
            retrieval_mode = "hybrid_rerank"
            logger.info(
                "[ADAPTIVE] site_id=%s rerank_triggered=True chunks_after_rerank=%d",
                site_id, len(chunks_for_llm),
            )
        else:
            retrieval_mode = "hybrid"

        # Determine if suggestions should be generated
        show_suggestions = config.show_suggestions if config else True

        # Build contact info string for LLM
        contact_info = None
        if config:
            parts = []
            if config.contact_email:
                parts.append(config.contact_email)
            if config.contact_phone:
                parts.append(config.contact_phone)
            if parts:
                contact_info = ", ".join(parts)

        # Generate answer with token-capped context
        result = await self.llm_service.generate_answer(
            question=question,
            context_chunks=chunks_for_llm,
            brand_name=config.brand_name if config else customer.name,
            tone=config.tone if config else "neutral",
            fallback_message=config.fallback_message if config else "I don't have that information yet.",
            max_tokens=config.max_response_length if config else 500,
            show_suggestions=show_suggestions,
            user_email=user_email,
            user_profile=user_profile,
            contact_info=contact_info,
            language=language,
            website_type=customer.website_type,
        )

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Compute fallback breakdown
        fallback_message = config.fallback_message if config else "I don't have that information yet."
        context_tokens = result.get("context_tokens", 0)

        retrieval_empty_flag = not vector_matches
        llm_declined = (
            result["answer"] == fallback_message
            and context_tokens > 0
        )
        fallback_triggered = retrieval_empty_flag or llm_declined

        # Log query
        query_log_id = await self._log_query(
            db=db,
            customer_id=customer.id,
            question=question,
            answer=result["answer"],
            chunks_used=len(chunks_for_llm),
            response_time_ms=response_time_ms,
            origin=origin,
            user_agent=user_agent,
            ip_address=ip_address,
            top_score=top_score,
            avg_score=avg_score,
            fallback_triggered=fallback_triggered,
            retrieval_mode=retrieval_mode,
            context_tokens=context_tokens,
            confidence_threshold=threshold,
            rerank_triggered=rerank_triggered,
            retrieval_empty=retrieval_empty_flag,
            llm_declined=llm_declined,
        )

        logger.info(
            "[RAG-METRICS] site_id=%s top_score=%.3f avg_score=%.3f fallback=%s mode=%s rerank=%s blocked=%s llm_declined=%s empty=%s context_tokens=%s",
            site_id, top_score or 0, avg_score or 0, fallback_triggered, retrieval_mode, rerank_triggered, False, llm_declined, retrieval_empty_flag, context_tokens,
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
            "_meta": {
                "top_score": top_score,
                "fallback_triggered": fallback_triggered,
                "llm_declined": llm_declined,
                "chunks_used": len(chunks_for_llm),
                "query_log_id": query_log_id,
            },
        }

    async def process_query_stream(
        self,
        db: AsyncSession,
        site_id: str,
        question: str,
        origin: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
        user_email: str | None = None,
        user_profile: dict | None = None,
        language: str | None = None,
    ):
        """
        Stream a query response. Yields SSE events:
        - {"type": "token", "data": "..."} for each text token
        - {"type": "done", "answer": "...", "suggestions": [...], "sources": [...]} at end
        """
        import time as _time
        start_time = _time.time()

        customer = await self._get_customer(db, site_id)
        if not customer:
            yield {"type": "error", "message": "Invalid site_id"}
            return

        if origin and not await self._validate_origin(db, customer.id, origin):
            yield {"type": "error", "message": "Origin domain not allowed"}
            return

        config = await self._get_widget_config(db, customer.id)

        # Embed + retrieve (same as process_query)
        query_embedding = await self.embedding_service.create_embedding(question)
        initial_fetch_k = 8

        vector_matches = await self.vector_store.query_vectors(
            query_vector=query_embedding, namespace=site_id,
            top_k=initial_fetch_k, site_id=site_id,
        )
        vector_ids = [m["id"] for m in vector_matches]
        vector_scores = [m["score"] for m in vector_matches]
        top_score = max(vector_scores) if vector_scores else None

        threshold = (
            config.confidence_threshold
            if config and config.confidence_threshold is not None
            else settings.confidence_threshold
        )

        if top_score is not None and top_score > 0.6:
            adaptive_top_k = 3
        elif top_score is not None and top_score >= 0.4:
            adaptive_top_k = 5
        else:
            adaptive_top_k = 8

        rerank_needed = (top_score is not None and top_score > threshold and top_score < 0.45)
        fusion_top_n = 8 if rerank_needed else adaptive_top_k

        keyword_query = f"{question} {user_email}" if user_email else question
        keyword_ids = await self._keyword_search(db, customer.id, keyword_query, limit=initial_fetch_k)

        fused_ids = _reciprocal_rank_fusion(vector_ids, keyword_ids, k=60, top_n=fusion_top_n)

        # No-data detection: check ingestion status for helpful messages
        if not fused_ids:
            status = await self._check_ingestion_status(db, customer.id)
            if status == "processing":
                msg = "I'm still learning about this website. Content is being indexed — please check back in a few minutes!"
                yield {"type": "token", "data": msg}
                yield {"type": "done", "answer": msg, "suggestions": [], "sources": []}
                return
            elif status == "empty":
                msg = "I'm still setting up and don't have information about this website yet. Please check back soon!"
                yield {"type": "token", "data": msg}
                yield {"type": "done", "answer": msg, "suggestions": [], "sources": []}
                return

        db_chunks = await self._fetch_chunks_by_vector_ids(db, fused_ids, customer.id)

        fused_rank = {vid: idx for idx, vid in enumerate(fused_ids)}
        chunks_for_llm = []
        for chunk in db_chunks:
            chunks_for_llm.append({
                "content": chunk.content,
                "source_url": chunk.source_url or "",
                "source_title": chunk.source_title or "Source",
                "score": len(fused_ids) - fused_rank.get(chunk.vector_id, len(fused_ids)),
            })
        chunks_for_llm.sort(key=lambda c: c["score"], reverse=True)

        if rerank_needed and len(chunks_for_llm) > 1:
            chunks_for_llm = await self.llm_service.rerank_chunks(question=question, chunks=chunks_for_llm, top_n=5)

        show_suggestions = config.show_suggestions if config else True

        contact_info = None
        if config:
            parts = []
            if config.contact_email:
                parts.append(config.contact_email)
            if config.contact_phone:
                parts.append(config.contact_phone)
            if parts:
                contact_info = ", ".join(parts)

        # Stream the LLM response
        full_answer = ""
        suggestions = []
        async for event in self.llm_service.generate_answer_stream(
            question=question,
            context_chunks=chunks_for_llm,
            brand_name=config.brand_name if config else customer.name,
            tone=config.tone if config else "neutral",
            fallback_message=config.fallback_message if config else "I don't have that information yet.",
            max_tokens=config.max_response_length if config else 500,
            show_suggestions=show_suggestions,
            user_email=user_email,
            user_profile=user_profile,
            contact_info=contact_info,
            language=language,
            website_type=customer.website_type,
        ):
            if event["type"] == "token":
                yield event
            elif event["type"] == "done":
                full_answer = event["answer"]
                suggestions = event["suggestions"]

        # Build sources
        sources = []
        seen_urls = set()
        for chunk in chunks_for_llm:
            url = chunk["source_url"]
            title = chunk["source_title"]
            if url and url not in seen_urls:
                sources.append({"title": title, "url": url})
                seen_urls.add(url)

        # Log query
        response_time_ms = int((_time.time() - start_time) * 1000)
        log_id = await self._log_query(
            db=db, customer_id=customer.id, question=question, answer=full_answer,
            chunks_used=len(chunks_for_llm), response_time_ms=response_time_ms,
            origin=origin, user_agent=user_agent, ip_address=ip_address,
            top_score=top_score,
        )

        yield {
            "type": "done",
            "answer": full_answer,
            "suggestions": suggestions if show_suggestions else [],
            "sources": sources if config and config.show_sources else [],
            "query_log_id": log_id,
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
            allowed_domain = allowed.domain.lower().strip().rstrip("/")
            # If stored value is a full URL, extract just the hostname
            if allowed_domain.startswith("http://") or allowed_domain.startswith("https://"):
                try:
                    allowed_domain = urlparse(allowed_domain).netloc.split(":")[0]
                except Exception:
                    pass
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
        top_score: float | None = None,
        avg_score: float | None = None,
        fallback_triggered: bool = False,
        retrieval_mode: str | None = None,
        context_tokens: int | None = None,
        confidence_threshold: float | None = None,
        rerank_triggered: bool = False,
        retrieval_blocked: bool = False,
        llm_declined: bool = False,
        retrieval_empty: bool = False,
    ) -> str | None:
        """Log query to database. Returns the log ID."""
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
            top_score=top_score,
            avg_score=avg_score,
            fallback_triggered=fallback_triggered,
            retrieval_mode=retrieval_mode,
            context_tokens=context_tokens,
            confidence_threshold=confidence_threshold,
            rerank_triggered=rerank_triggered,
            retrieval_blocked=retrieval_blocked,
            llm_declined=llm_declined,
            retrieval_empty=retrieval_empty,
        )
        db.add(log)
        await db.commit()
        return str(log.id)


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
