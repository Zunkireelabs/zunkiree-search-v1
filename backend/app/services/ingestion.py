import uuid
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models import Customer, IngestionJob, DocumentChunk
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service
from app.utils.chunking import chunk_text
from app.utils.crawling import crawl_url, extract_text_from_pdf
from app.utils.file_parsers import extract_pdf_text, extract_docx_text, extract_plain_text

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 300


class IngestionService:
    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store_service()

    async def ingest_url(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
        url: str,
        depth: int = 0,
        max_pages: int = 1,
    ) -> IngestionJob:
        """
        Ingest content from a URL.

        Args:
            db: Database session
            customer_id: Customer UUID
            site_id: Customer site ID (Pinecone namespace)
            url: URL to crawl
            depth: Crawl depth (0 = single page)
            max_pages: Maximum pages to crawl

        Returns:
            IngestionJob record
        """
        # Create job record
        job = IngestionJob(
            customer_id=customer_id,
            source_type="url",
            source_url=url,
            status="processing",
            started_at=datetime.utcnow(),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        try:
            # Crawl URLs
            pages_to_process = [url]
            processed_urls = set()
            all_chunks = []

            while pages_to_process and len(processed_urls) < max_pages:
                current_url = pages_to_process.pop(0)

                if current_url in processed_urls:
                    continue

                processed_urls.add(current_url)

                try:
                    # Crawl the page
                    page_data = await crawl_url(current_url)

                    # Chunk the content
                    chunks = chunk_text(page_data["content"])

                    for chunk in chunks:
                        chunk["source_url"] = current_url
                        chunk["source_title"] = page_data["title"]
                        all_chunks.append(chunk)

                    # Add links to queue if depth > 0
                    if depth > 0 and len(processed_urls) < max_pages:
                        for link in page_data["links"][:10]:  # Limit links per page
                            if link not in processed_urls:
                                pages_to_process.append(link)

                except Exception as e:
                    print(f"Error crawling {current_url}: {e}")
                    continue

            # Generate embeddings and store
            if all_chunks:
                await self._process_chunks(
                    db=db,
                    job=job,
                    site_id=site_id,
                    chunks=all_chunks,
                )

            # Update job status
            job.status = "completed"
            job.chunks_created = len(all_chunks)
            job.completed_at = datetime.utcnow()
            await db.commit()

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            raise

        return job

    async def ingest_text(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
        text: str,
        source_title: str = "Uploaded Text",
    ) -> IngestionJob:
        """
        Ingest raw text content.

        Args:
            db: Database session
            customer_id: Customer UUID
            site_id: Customer site ID (Pinecone namespace)
            text: Text content to ingest
            source_title: Title for the content

        Returns:
            IngestionJob record
        """
        # Create job record
        job = IngestionJob(
            customer_id=customer_id,
            source_type="text",
            source_filename=source_title,
            status="processing",
            started_at=datetime.utcnow(),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        try:
            # Chunk the content
            chunks = chunk_text(text)

            for chunk in chunks:
                chunk["source_title"] = source_title

            # Process chunks
            if chunks:
                await self._process_chunks(
                    db=db,
                    job=job,
                    site_id=site_id,
                    chunks=chunks,
                )

            # Update job status
            job.status = "completed"
            job.chunks_created = len(chunks)
            job.completed_at = datetime.utcnow()
            await db.commit()

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            raise

        return job

    async def ingest_pdf(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
        pdf_content: bytes,
        filename: str,
    ) -> IngestionJob:
        """
        Ingest content from a PDF file.

        Args:
            db: Database session
            customer_id: Customer UUID
            site_id: Customer site ID (Pinecone namespace)
            pdf_content: PDF file bytes
            filename: Original filename

        Returns:
            IngestionJob record
        """
        # Create job record
        job = IngestionJob(
            customer_id=customer_id,
            source_type="pdf",
            source_filename=filename,
            status="processing",
            started_at=datetime.utcnow(),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        try:
            # Extract text from PDF
            text = await extract_text_from_pdf(pdf_content)

            # Chunk the content
            chunks = chunk_text(text)

            for chunk in chunks:
                chunk["source_title"] = filename

            # Process chunks
            if chunks:
                await self._process_chunks(
                    db=db,
                    job=job,
                    site_id=site_id,
                    chunks=chunks,
                )

            # Update job status
            job.status = "completed"
            job.chunks_created = len(chunks)
            job.completed_at = datetime.utcnow()
            await db.commit()

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            raise

        return job

    async def ingest_file(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
        file_bytes: bytes,
        filename: str,
        source_type: str,
    ) -> IngestionJob:
        """
        Ingest content from an uploaded file (PDF, DOCX, or plain text).

        Args:
            db: Database session
            customer_id: Customer UUID
            site_id: Customer site ID (Pinecone namespace)
            file_bytes: Raw file bytes
            filename: Original filename
            source_type: File type — "pdf", "docx", or "text"

        Returns:
            IngestionJob record
        """
        job = IngestionJob(
            customer_id=customer_id,
            source_type=source_type,
            source_filename=filename,
            status="processing",
            started_at=datetime.utcnow(),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        try:
            # Extract text based on source type
            if source_type == "pdf":
                text = extract_pdf_text(file_bytes)
            elif source_type == "docx":
                text = extract_docx_text(file_bytes)
            else:
                text = extract_plain_text(file_bytes)

            # Content guard
            if len(text.strip()) < MIN_CONTENT_LENGTH:
                job.status = "failed"
                job.error_message = f"Insufficient content extracted ({len(text.strip())} chars, minimum {MIN_CONTENT_LENGTH})"
                job.completed_at = datetime.utcnow()
                await db.commit()
                logger.warning("File ingestion failed: insufficient content from %s (%d chars)", filename, len(text.strip()))
                return job

            # Chunk the content
            chunks = chunk_text(text)
            for chunk in chunks:
                chunk["source_title"] = filename

            # Process chunks
            if chunks:
                await self._process_chunks(
                    db=db,
                    job=job,
                    site_id=site_id,
                    chunks=chunks,
                )

            job.status = "completed"
            job.chunks_created = len(chunks)
            job.completed_at = datetime.utcnow()
            await db.commit()
            logger.info("File ingestion completed: %s → %d chunks", filename, len(chunks))

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            raise

        return job

    async def ingest_qa(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
        question: str,
        answer: str,
    ) -> IngestionJob:
        """
        Ingest a Q&A seed pair as a knowledge chunk.

        Args:
            db: Database session
            customer_id: Customer UUID
            site_id: Customer site ID (Pinecone namespace)
            question: The question
            answer: The answer

        Returns:
            IngestionJob record
        """
        job = IngestionJob(
            customer_id=customer_id,
            source_type="qa_seed",
            source_filename=f"QA: {question[:80]}",
            status="processing",
            started_at=datetime.utcnow(),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        try:
            # Combine Q&A into a single text block
            text = f"Q: {question}\nA: {answer}"

            # Chunk normally (most QA pairs will be a single chunk)
            chunks = chunk_text(text)
            for chunk in chunks:
                chunk["source_title"] = f"QA: {question[:80]}"

            if chunks:
                await self._process_chunks(
                    db=db,
                    job=job,
                    site_id=site_id,
                    chunks=chunks,
                )

            job.status = "completed"
            job.chunks_created = len(chunks)
            job.completed_at = datetime.utcnow()
            await db.commit()
            logger.info("QA seed ingested: %d chunks for site %s", len(chunks), site_id)

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            raise

        return job

    async def _process_chunks(
        self,
        db: AsyncSession,
        job: IngestionJob,
        site_id: str,
        chunks: list[dict],
    ) -> None:
        """Process chunks: generate embeddings and store in vector DB."""
        # Extract content for embedding
        texts = [chunk["content"] for chunk in chunks]

        # Generate embeddings in batches
        batch_size = 100
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = await self.embedding_service.create_embeddings(batch)
            all_embeddings.extend(embeddings)

        # Prepare vectors for Pinecone
        vectors = []
        for i, (chunk, embedding) in enumerate(zip(chunks, all_embeddings)):
            vector_id = f"{job.id}_{i}"

            vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": {
                    "source_url": chunk.get("source_url", ""),
                    "source_title": chunk.get("source_title", ""),
                    "chunk_index": chunk["chunk_index"],
                    "job_id": str(job.id),
                    "site_id": site_id,
                },
            })

            # Create document chunk record with full content in Postgres
            doc_chunk = DocumentChunk(
                customer_id=job.customer_id,
                job_id=job.id,
                vector_id=vector_id,
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                content_preview=chunk["content"][:500],
                source_url=chunk.get("source_url"),
                source_title=chunk.get("source_title"),
                token_count=chunk.get("token_count"),
            )
            db.add(doc_chunk)

        # Upsert to Pinecone
        await self.vector_store.upsert_vectors(vectors, namespace=site_id)

        # Commit document chunks
        await db.commit()

        # Backfill search_vector for full-text search
        vector_ids = [v["id"] for v in vectors]
        await db.execute(
            text("""
                UPDATE document_chunks
                SET search_vector = to_tsvector('english', content)
                WHERE vector_id = ANY(:vector_ids)
                AND search_vector IS NULL
            """),
            {"vector_ids": vector_ids},
        )
        await db.commit()

    async def delete_customer_data(
        self,
        db: AsyncSession,
        site_id: str,
    ) -> None:
        """Delete all vectors for a customer (for re-indexing)."""
        await self.vector_store.delete_namespace(site_id)


# Singleton instance
_ingestion_service: IngestionService | None = None


def get_ingestion_service() -> IngestionService:
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = IngestionService()
    return _ingestion_service
