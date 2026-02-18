import uuid
import secrets
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Customer, Domain, WidgetConfig, IngestionJob, DocumentChunk
from app.services.ingestion import get_ingestion_service
from app.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


# Authentication dependency
async def verify_admin_key(x_admin_key: str = Header(...)):
    if x_admin_key != settings.api_secret_key:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid admin key"},
        )
    return x_admin_key


# Request/Response models
class CreateCustomerRequest(BaseModel):
    name: str = Field(..., description="Customer display name")
    site_id: str = Field(..., pattern="^[a-z0-9-]+$", description="Unique site identifier (lowercase, alphanumeric, hyphens)")
    allowed_domains: list[str] = Field(..., description="List of allowed domains")


class CreateCustomerResponse(BaseModel):
    id: str
    site_id: str
    api_key: str
    message: str


class IngestUrlRequest(BaseModel):
    customer_id: str = Field(..., description="Customer site_id")
    url: str = Field(..., description="URL to crawl")
    depth: int = Field(0, ge=0, le=2, description="Crawl depth (0 = single page)")
    max_pages: int = Field(1, ge=1, le=50, description="Maximum pages to crawl")


class IngestTextRequest(BaseModel):
    customer_id: str = Field(..., description="Customer site_id")
    text: str = Field(..., min_length=10, description="Text content to ingest")
    title: str = Field("Uploaded Content", description="Title for the content")


class IngestQARequest(BaseModel):
    site_id: str = Field(..., description="Customer site_id")
    question: str = Field(..., min_length=5, description="The question")
    answer: str = Field(..., min_length=10, description="The answer")


class QAPair(BaseModel):
    question: str = Field(..., min_length=5, description="The question")
    answer: str = Field(..., min_length=10, description="The answer")


class IngestQABatchRequest(BaseModel):
    site_id: str = Field(..., description="Customer site_id")
    qa_pairs: list[QAPair] = Field(..., min_length=1, max_length=50, description="Q&A pairs to ingest")


class QABatchJobResult(BaseModel):
    question: str
    job_id: str
    status: str
    chunks_created: int


class QABatchResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[QABatchJobResult]


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class UpdateConfigRequest(BaseModel):
    brand_name: str | None = None
    tone: str | None = Field(None, pattern="^(formal|neutral|friendly)$")
    primary_color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    placeholder_text: str | None = None
    welcome_message: str | None = None
    fallback_message: str | None = None
    show_sources: bool | None = None
    show_suggestions: bool | None = None


class JobInfo(BaseModel):
    id: str
    source_type: str
    source_url: str | None
    source_filename: str | None
    status: str
    chunks_created: int
    created_at: str
    completed_at: str | None


class JobsListResponse(BaseModel):
    jobs: list[JobInfo]
    total: int


class CustomerInfo(BaseModel):
    id: str
    name: str
    site_id: str
    is_active: bool
    created_at: str


class CustomersListResponse(BaseModel):
    customers: list[CustomerInfo]


class TenantStatsResponse(BaseModel):
    site_id: str
    brand_name: str
    total_chunks: int
    total_jobs: int
    last_ingestion_date: str | None


# Endpoints
@router.post("/customers", response_model=CreateCustomerResponse)
async def create_customer(
    request: CreateCustomerRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Create a new customer."""
    # Check if site_id already exists
    result = await db.execute(
        select(Customer).where(Customer.site_id == request.site_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail={"code": "DUPLICATE_SITE_ID", "message": "Site ID already exists"},
        )

    # Generate API key
    api_key = f"zk_live_{request.site_id}_{secrets.token_urlsafe(24)}"

    # Create customer
    customer = Customer(
        name=request.name,
        site_id=request.site_id,
        api_key=api_key,
    )
    db.add(customer)
    await db.flush()

    # Create domains
    for domain in request.allowed_domains:
        domain_record = Domain(
            customer_id=customer.id,
            domain=domain.lower().strip(),
        )
        db.add(domain_record)

    # Create default widget config
    config = WidgetConfig(
        customer_id=customer.id,
        brand_name=request.name,
    )
    db.add(config)

    await db.commit()

    return CreateCustomerResponse(
        id=str(customer.id),
        site_id=customer.site_id,
        api_key=api_key,
        message="Customer created successfully",
    )


@router.get("/customers", response_model=CustomersListResponse)
async def list_customers(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """List all customers."""
    result = await db.execute(
        select(Customer).order_by(Customer.created_at.desc())
    )
    customers = result.scalars().all()

    return CustomersListResponse(
        customers=[
            CustomerInfo(
                id=str(c.id),
                name=c.name,
                site_id=c.site_id,
                is_active=c.is_active,
                created_at=c.created_at.isoformat(),
            )
            for c in customers
        ]
    )


@router.get("/stats/{site_id}", response_model=TenantStatsResponse)
async def get_tenant_stats(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Get ingestion stats for a tenant."""
    result = await db.execute(
        select(Customer).where(Customer.site_id == site_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    # Total chunks
    chunk_count = await db.execute(
        select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.customer_id == customer.id
        )
    )
    total_chunks = chunk_count.scalar() or 0

    # Total jobs + last ingestion date
    job_stats = await db.execute(
        select(
            func.count(),
            func.max(IngestionJob.completed_at),
        ).where(IngestionJob.customer_id == customer.id)
    )
    row = job_stats.one()
    total_jobs = row[0] or 0
    last_ingestion = row[1]

    # Brand name from config
    config_result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )
    config = config_result.scalar_one_or_none()
    brand_name = config.brand_name if config else customer.name

    return TenantStatsResponse(
        site_id=site_id,
        brand_name=brand_name,
        total_chunks=total_chunks,
        total_jobs=total_jobs,
        last_ingestion_date=last_ingestion.isoformat() if last_ingestion else None,
    )


@router.post("/ingest/url", response_model=JobResponse)
async def ingest_url(
    request: IngestUrlRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Ingest content from a URL."""
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == request.customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    ingestion_service = get_ingestion_service()

    try:
        job = await ingestion_service.ingest_url(
            db=db,
            customer_id=customer.id,
            site_id=customer.site_id,
            url=request.url,
            depth=request.depth,
            max_pages=request.max_pages,
        )

        return JobResponse(
            job_id=str(job.id),
            status=job.status,
            message=f"Ingestion completed. {job.chunks_created} chunks created.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "INGESTION_FAILED", "message": str(e)},
        )


@router.post("/ingest/text", response_model=JobResponse)
async def ingest_text(
    request: IngestTextRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Ingest raw text content."""
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == request.customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    ingestion_service = get_ingestion_service()

    try:
        job = await ingestion_service.ingest_text(
            db=db,
            customer_id=customer.id,
            site_id=customer.site_id,
            text=request.text,
            source_title=request.title,
        )

        return JobResponse(
            job_id=str(job.id),
            status=job.status,
            message=f"Ingestion completed. {job.chunks_created} chunks created.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "INGESTION_FAILED", "message": str(e)},
        )


ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "text",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/ingest/file", response_model=JobResponse)
async def ingest_file(
    site_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Upload and ingest a document (PDF, DOCX, or TXT)."""
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == site_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    # Validate file extension
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_FILE_TYPE", "message": f"Allowed types: {', '.join(ALLOWED_EXTENSIONS.keys())}"},
        )

    source_type = ALLOWED_EXTENSIONS[ext]

    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": f"Maximum file size is {MAX_FILE_SIZE // (1024*1024)}MB"},
        )

    ingestion_service = get_ingestion_service()

    try:
        job = await ingestion_service.ingest_file(
            db=db,
            customer_id=customer.id,
            site_id=customer.site_id,
            file_bytes=content,
            filename=filename,
            source_type=source_type,
        )

        return JobResponse(
            job_id=str(job.id),
            status=job.status,
            message=f"Ingestion {job.status}. {job.chunks_created} chunks created.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "INGESTION_FAILED", "message": str(e)},
        )


@router.post("/ingest/qa", response_model=JobResponse)
async def ingest_qa(
    request: IngestQARequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Ingest a Q&A seed pair as structured knowledge."""
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == request.site_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    ingestion_service = get_ingestion_service()

    try:
        job = await ingestion_service.ingest_qa(
            db=db,
            customer_id=customer.id,
            site_id=customer.site_id,
            question=request.question,
            answer=request.answer,
        )

        return JobResponse(
            job_id=str(job.id),
            status=job.status,
            message=f"QA seed ingested. {job.chunks_created} chunks created.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "INGESTION_FAILED", "message": str(e)},
        )


@router.post("/ingest/qa/batch", response_model=QABatchResponse)
async def ingest_qa_batch(
    request: IngestQABatchRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Ingest multiple Q&A seed pairs in a single request."""
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == request.site_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    ingestion_service = get_ingestion_service()
    results = []
    succeeded = 0
    failed = 0

    for pair in request.qa_pairs:
        try:
            job = await ingestion_service.ingest_qa(
                db=db,
                customer_id=customer.id,
                site_id=customer.site_id,
                question=pair.question,
                answer=pair.answer,
            )
            results.append(QABatchJobResult(
                question=pair.question[:80],
                job_id=str(job.id),
                status=job.status,
                chunks_created=job.chunks_created,
            ))
            if job.status == "completed":
                succeeded += 1
            else:
                failed += 1
        except Exception:
            failed += 1
            results.append(QABatchJobResult(
                question=pair.question[:80],
                job_id="",
                status="failed",
                chunks_created=0,
            ))

    return QABatchResponse(
        total=len(request.qa_pairs),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


@router.put("/config/{customer_id}")
async def update_config(
    customer_id: str,
    request: UpdateConfigRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Update widget configuration for a customer."""
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    # Get or create config
    result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )
    config = result.scalar_one_or_none()

    if not config:
        config = WidgetConfig(
            customer_id=customer.id,
            brand_name=customer.name,
        )
        db.add(config)

    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(config, field, value)

    await db.commit()

    return {"message": "Config updated successfully"}


@router.get("/jobs/{customer_id}", response_model=JobsListResponse)
async def list_jobs(
    customer_id: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """List ingestion jobs for a customer."""
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    # Build query
    query = select(IngestionJob).where(IngestionJob.customer_id == customer.id)

    if status:
        query = query.where(IngestionJob.status == status)

    query = query.order_by(IngestionJob.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobsListResponse(
        jobs=[
            JobInfo(
                id=str(job.id),
                source_type=job.source_type,
                source_url=job.source_url,
                source_filename=job.source_filename,
                status=job.status,
                chunks_created=job.chunks_created,
                created_at=job.created_at.isoformat(),
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
            )
            for job in jobs
        ],
        total=len(jobs),
    )


@router.post("/reindex/{customer_id}", response_model=JobResponse)
async def reindex_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Delete all vectors for a customer (for re-indexing)."""
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    ingestion_service = get_ingestion_service()

    try:
        await ingestion_service.delete_customer_data(
            db=db,
            site_id=customer.site_id,
        )

        return JobResponse(
            job_id="",
            status="completed",
            message="All vectors deleted. Ready for re-indexing.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "REINDEX_FAILED", "message": str(e)},
        )
