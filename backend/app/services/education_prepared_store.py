"""The concrete store behind `education_prepared_ingest`: Postgres + Pinecone, through the EXISTING ingestion pipeline.

Not wired to anything: no command, route or script uses it, and it does not exist as a default. To use it, a future, separately
approved task must hand in a database session, an `IngestionService`, a vector store and the target explicitly, and enable writes
explicitly. This module imports no client factory, no session maker and no settings, so it cannot reach a real service on its own.

Every statement is scoped to the target customer and to exact job ids. Chunks are written by the unchanged
`IngestionService._process_chunks` (embeddings, Postgres rows committed first, then vectors), so they carry the canonical source
url and title in both stores. There is no namespace-wide operation of any kind here.
"""
import uuid
from datetime import datetime

from sqlalchemy import delete, func, select

from app.models.customer import Customer
from app.models.ingestion import DocumentChunk, IngestionJob
from app.services.education_ingest_plan import PageWriteError
from app.services.education_prepared_ingest import JobState, PreparedPage, Target, TargetInfo, Verification, WriteResult


class WritesNotEnabled(RuntimeError):
    pass


def _job_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as e:
        raise ValueError(f"not a job id: {value!r}") from e


class SqlPineconeStore:
    def __init__(self, *, db, ingestion_service, vector_store, target: Target, allow_real_writes: bool = False):
        if any(dependency is None for dependency in (db, ingestion_service, vector_store, target)):
            raise TypeError("db, ingestion_service, vector_store and target must all be handed in explicitly")
        if not isinstance(allow_real_writes, bool):
            raise TypeError("allow_real_writes must be exactly True or False")
        self._db, self._ingestion, self._vectors, self._target, self._writes = db, ingestion_service, vector_store, target, allow_real_writes

    @property
    def writes_enabled(self) -> bool:
        return self._writes

    def _require_writes(self) -> None:
        if not self._writes:
            raise WritesNotEnabled("this store was created with allow_real_writes=False")

    # --- reads -------------------------------------------------------------------------------------------------------------

    async def describe_target(self) -> TargetInfo:
        customer = (await self._db.execute(select(Customer).where(Customer.id == self._target.customer_id))).scalar_one_or_none()
        if customer is None:
            return TargetInfo(site_id="", customer_id=uuid.UUID(int=0), website_type="", namespace="")
        return TargetInfo(site_id=customer.site_id, customer_id=customer.id, website_type=customer.website_type or "",
                          namespace=self._target.namespace)

    async def _rows(self, job_id: uuid.UUID) -> int:
        return (await self._db.execute(select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.job_id == job_id, DocumentChunk.customer_id == self._target.customer_id))).scalar_one()

    async def _existing(self, ids: list[str]) -> set[str]:
        return await self._vectors.existing_ids(ids, self._target.namespace) if ids else set()

    async def jobs_for_url(self, canonical_url: str) -> list[JobState]:
        jobs = (await self._db.execute(select(IngestionJob).where(
            IngestionJob.customer_id == self._target.customer_id, IngestionJob.source_url == canonical_url))).scalars().all()
        states = []
        for job in jobs:
            rows = await self._rows(job.id)
            expected = max(job.chunks_created or 0, rows)
            vectors = len(await self._existing([f"{job.id}_{i}" for i in range(expected)]))
            states.append(JobState(job_id=str(job.id), status=job.status, source_url=job.source_url, title=job.source_filename,
                                   chunks_expected=job.chunks_created or 0, rows=rows, vectors=vectors))
        return states

    async def verify_job(self, job_id: str, expected_chunks: int) -> Verification:
        jid = _job_uuid(job_id)
        rows = await self._rows(jid)
        return Verification(rows=rows, vectors=len(await self._existing([f"{jid}_{i}" for i in range(expected_chunks)])))

    async def job_vector_ids(self, job_id: str) -> list[str]:
        jid = _job_uuid(job_id)
        return list((await self._db.execute(select(DocumentChunk.vector_id).where(
            DocumentChunk.job_id == jid, DocumentChunk.customer_id == self._target.customer_id).order_by(DocumentChunk.chunk_index))).scalars().all())

    # --- writes (each one refuses unless writes were explicitly enabled) ------------------------------------------------------------

    async def write_page(self, page: PreparedPage) -> WriteResult:
        self._require_writes()
        job = IngestionJob(id=page.job_id, customer_id=self._target.customer_id, source_type="url", source_url=page.canonical_url,
                           source_filename=page.title, status="processing", started_at=datetime.utcnow())
        self._db.add(job)
        await self._db.commit()
        await self._db.refresh(job)
        try:
            await self._ingestion._process_chunks(db=self._db, job=job, site_id=self._target.site_id, chunks=page.chunks)
            job.status, job.chunks_created, job.completed_at = "completed", len(page.chunks), datetime.utcnow()
            await self._db.commit()
        except Exception as error:
            job.status, job.error_message, job.completed_at = "failed", str(error), datetime.utcnow()
            await self._db.commit()
            raise PageWriteError(str(error), job_id=str(page.job_id)) from error
        return WriteResult(job_id=str(page.job_id), rows=len(page.chunks), vectors=len(page.chunks))

    async def delete_vectors(self, ids: list[str]) -> None:
        self._require_writes()
        if ids:
            await self._vectors.delete_vectors(list(ids), self._target.namespace)

    async def delete_job(self, job_id: str) -> None:
        self._require_writes()
        await self._db.execute(delete(IngestionJob).where(IngestionJob.id == _job_uuid(job_id), IngestionJob.customer_id == self._target.customer_id))
        await self._db.commit()

    async def cleanup_job(self, job_id: str) -> None:
        """Remove ONE job this adapter wrote (its vectors first, then the job and, by cascade, its rows). Never anything else."""
        self._require_writes()
        jid = _job_uuid(job_id)
        ids = set(await self.job_vector_ids(job_id))
        job = (await self._db.execute(select(IngestionJob).where(
            IngestionJob.id == jid, IngestionJob.customer_id == self._target.customer_id))).scalar_one_or_none()
        if job is not None:
            ids |= {f"{jid}_{i}" for i in range(job.chunks_created or 0)}
        await self.delete_vectors(sorted(ids))
        await self.delete_job(job_id)
