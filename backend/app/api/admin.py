import uuid
import csv
import io
import secrets
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Integer, select, func, case, delete

from app.database import get_db
from app.models import Customer, Domain, WidgetConfig, IngestionJob, DocumentChunk, QueryLog, UserProfile, Product
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
    contact_email: str | None = Field(None, description="Customer contact email for welcome email")


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
    confidence_threshold: float | None = Field(None, ge=0.1, le=0.5)
    enable_identity_verification: bool | None = None
    identity_custom_fields: str | None = None  # JSON array of {"key", "label", "required"}
    lead_intents: str | None = None  # JSON array of lead intent configs
    contact_email: str | None = None
    contact_phone: str | None = None
    supported_languages: str | None = None  # JSON array e.g. '["en", "ne"]'


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


class ModeCount(BaseModel):
    mode: str
    count: int


class RetrievalStatsResponse(BaseModel):
    total_queries: int
    fallback_rate: float
    blocked_rate: float
    llm_decline_rate: float
    retrieval_empty_rate: float
    avg_top_score: float | None
    avg_response_time: float | None
    threshold_guard_rate: float
    avg_context_tokens: float | None
    mode_breakdown: list[ModeCount]
    health_score: float


class LeadInfo(BaseModel):
    id: str
    email: str
    name: str
    phone: str | None
    location: str | None
    user_type: str | None
    lead_intent: str | None
    custom_fields: str | None
    created_at: str
    updated_at: str


class LeadsListResponse(BaseModel):
    leads: list[LeadInfo]
    total: int
    page: int
    page_size: int


class QueryLogInfo(BaseModel):
    id: str
    question: str
    answer_preview: str | None
    top_score: float | None
    response_time_ms: int | None
    retrieval_mode: str | None
    fallback_triggered: bool
    origin_domain: str | None
    created_at: str


class QueryLogsListResponse(BaseModel):
    queries: list[QueryLogInfo]
    total: int
    page: int
    page_size: int


# Endpoints
@router.post("/customers", response_model=CreateCustomerResponse)
async def create_customer(
    request: CreateCustomerRequest,
    background_tasks: BackgroundTasks,
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

    # Queue auto-ingestion for allowed domains
    if request.allowed_domains:
        from app.services.auto_ingest import run_auto_ingestion
        background_tasks.add_task(
            run_auto_ingestion,
            customer.id,
            customer.site_id,
            request.allowed_domains,
        )

    # Send welcome email if contact_email provided
    if request.contact_email:
        from app.services.email import send_welcome_email
        await send_welcome_email(
            to_email=request.contact_email,
            customer_name=request.name,
            site_id=request.site_id,
            api_key=api_key,
        )

    return CreateCustomerResponse(
        id=str(customer.id),
        site_id=customer.site_id,
        api_key=api_key,
        message="Customer created successfully. Auto-ingestion queued for allowed domains.",
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


@router.get("/customers/{site_id}/api-key")
async def get_customer_api_key(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Get API key for a customer (admin only)."""
    result = await db.execute(
        select(Customer).where(Customer.site_id == site_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )
    return {"api_key": customer.api_key}


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


@router.get("/retrieval-stats/{site_id}", response_model=RetrievalStatsResponse)
async def get_retrieval_stats(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Get retrieval health metrics for a tenant (last 7 days)."""
    result = await db.execute(
        select(Customer).where(Customer.site_id == site_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )

    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(days=7)

    # Single aggregation query for all scalar metrics + fallback breakdown
    agg = await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((QueryLog.fallback_triggered == True, 1), else_=0)).label("fallback_count"),
            func.sum(case((QueryLog.retrieval_blocked == True, 1), else_=0)).label("blocked_count"),
            func.sum(case((QueryLog.llm_declined == True, 1), else_=0)).label("llm_decline_count"),
            func.sum(case((QueryLog.retrieval_empty == True, 1), else_=0)).label("empty_count"),
            func.avg(QueryLog.top_score).label("avg_top_score"),
            func.avg(QueryLog.response_time_ms).label("avg_response_time"),
            func.avg(QueryLog.context_tokens).label("avg_context_tokens"),
        ).where(
            QueryLog.customer_id == customer.id,
            QueryLog.created_at >= since,
        )
    )
    row = agg.one()
    total = row.total or 0
    fallback_count = int(row.fallback_count or 0)
    blocked_count = int(row.blocked_count or 0)
    llm_decline_count = int(row.llm_decline_count or 0)
    empty_count = int(row.empty_count or 0)
    avg_top = round(float(row.avg_top_score), 3) if row.avg_top_score is not None else None
    avg_rt = round(float(row.avg_response_time), 0) if row.avg_response_time is not None else None
    avg_ctx = round(float(row.avg_context_tokens), 0) if row.avg_context_tokens is not None else None

    # Threshold guard count (retrieval_mode = 'hybrid_threshold')
    tg = await db.execute(
        select(func.count()).select_from(QueryLog).where(
            QueryLog.customer_id == customer.id,
            QueryLog.created_at >= since,
            QueryLog.retrieval_mode == "hybrid_threshold",
        )
    )
    threshold_count = tg.scalar() or 0

    # Mode breakdown
    modes = await db.execute(
        select(
            QueryLog.retrieval_mode,
            func.count().label("cnt"),
        ).where(
            QueryLog.customer_id == customer.id,
            QueryLog.created_at >= since,
            QueryLog.retrieval_mode.isnot(None),
        ).group_by(QueryLog.retrieval_mode)
    )
    mode_breakdown = [ModeCount(mode=r[0], count=r[1]) for r in modes.fetchall()]

    # Compute rates for return + health score
    fallback_rate = round((fallback_count / total) * 100, 1) if total > 0 else 0.0
    blocked_rate = round((blocked_count / total) * 100, 1) if total > 0 else 0.0
    llm_decline_rate = round((llm_decline_count / total) * 100, 1) if total > 0 else 0.0
    retrieval_empty_rate = round((empty_count / total) * 100, 1) if total > 0 else 0.0
    threshold_guard_rate = round((threshold_count / total) * 100, 1) if total > 0 else 0.0

    # Health score (0–100) — Phase 4F refined formula
    if total == 0:
        health_score = 0.0
    else:
        score_component = min((avg_top or 0) / 0.7, 1.0) * 30
        context_component = min((avg_ctx or 0) / 800, 1.0) * 10
        threshold_component = (1 - blocked_rate / 100) * 20
        llm_penalty = (llm_decline_rate / 100) * 25
        empty_penalty = (retrieval_empty_rate / 100) * 40
        raw = score_component + context_component + threshold_component - llm_penalty - empty_penalty
        health_score = round(max(0.0, min(100.0, raw)), 1)

    return RetrievalStatsResponse(
        total_queries=total,
        fallback_rate=fallback_rate,
        blocked_rate=blocked_rate,
        llm_decline_rate=llm_decline_rate,
        retrieval_empty_rate=retrieval_empty_rate,
        avg_top_score=avg_top,
        avg_response_time=avg_rt,
        threshold_guard_rate=threshold_guard_rate,
        avg_context_tokens=avg_ctx,
        mode_breakdown=mode_breakdown,
        health_score=health_score,
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


# --- Tenant Data Visibility Endpoints ---

async def _resolve_customer(site_id: str, db: AsyncSession) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.site_id == site_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"},
        )
    return customer


@router.get("/leads/{site_id}", response_model=LeadsListResponse)
async def list_leads(
    site_id: str,
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Paginated list of leads/users for a tenant."""
    customer = await _resolve_customer(site_id, db)

    base = select(UserProfile).where(UserProfile.customer_id == customer.id)
    count_base = select(func.count()).select_from(UserProfile).where(
        UserProfile.customer_id == customer.id
    )

    if search:
        like = f"%{search}%"
        base = base.where(
            (UserProfile.email.ilike(like)) | (UserProfile.name.ilike(like))
        )
        count_base = count_base.where(
            (UserProfile.email.ilike(like)) | (UserProfile.name.ilike(like))
        )

    total = (await db.execute(count_base)).scalar() or 0

    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            base.order_by(UserProfile.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    return LeadsListResponse(
        leads=[
            LeadInfo(
                id=str(u.id),
                email=u.email,
                name=u.name,
                phone=u.phone,
                location=u.location,
                user_type=u.user_type,
                lead_intent=u.lead_intent,
                custom_fields=u.custom_fields,
                created_at=u.created_at.isoformat(),
                updated_at=u.updated_at.isoformat(),
            )
            for u in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/leads/{site_id}/export")
async def export_leads(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """CSV export of all leads for a tenant."""
    customer = await _resolve_customer(site_id, db)

    rows = (
        await db.execute(
            select(UserProfile)
            .where(UserProfile.customer_id == customer.id)
            .order_by(UserProfile.created_at.desc())
        )
    ).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "name", "phone", "location", "user_type", "lead_intent", "custom_fields", "created_at"])
    for u in rows:
        writer.writerow([u.email, u.name, u.phone, u.location, u.user_type, u.lead_intent, u.custom_fields, u.created_at.isoformat()])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={site_id}_leads.csv"},
    )


@router.delete("/leads/{site_id}/{lead_id}")
async def delete_lead(
    site_id: str,
    lead_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Delete a lead (GDPR compliance)."""
    customer = await _resolve_customer(site_id, db)

    result = await db.execute(
        delete(UserProfile).where(
            UserProfile.id == uuid.UUID(lead_id),
            UserProfile.customer_id == customer.id,
        )
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail={"code": "LEAD_NOT_FOUND", "message": "Lead not found"},
        )

    await db.commit()
    return {"message": "Lead deleted successfully"}


@router.get("/queries/{site_id}", response_model=QueryLogsListResponse)
async def list_queries(
    site_id: str,
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Paginated query history for a tenant."""
    customer = await _resolve_customer(site_id, db)

    base = select(QueryLog).where(QueryLog.customer_id == customer.id)
    count_base = select(func.count()).select_from(QueryLog).where(
        QueryLog.customer_id == customer.id
    )

    if search:
        like = f"%{search}%"
        base = base.where(QueryLog.question.ilike(like))
        count_base = count_base.where(QueryLog.question.ilike(like))

    total = (await db.execute(count_base)).scalar() or 0

    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            base.order_by(QueryLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    return QueryLogsListResponse(
        queries=[
            QueryLogInfo(
                id=str(q.id),
                question=q.question,
                answer_preview=q.answer[:200] if q.answer else None,
                top_score=round(q.top_score, 3) if q.top_score is not None else None,
                response_time_ms=q.response_time_ms,
                retrieval_mode=q.retrieval_mode,
                fallback_triggered=q.fallback_triggered,
                origin_domain=q.origin_domain,
                created_at=q.created_at.isoformat(),
            )
            for q in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/queries/{site_id}/export")
async def export_queries(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """CSV export of all queries for a tenant."""
    customer = await _resolve_customer(site_id, db)

    rows = (
        await db.execute(
            select(QueryLog)
            .where(QueryLog.customer_id == customer.id)
            .order_by(QueryLog.created_at.desc())
        )
    ).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["question", "answer", "top_score", "response_time_ms", "retrieval_mode", "fallback_triggered", "origin_domain", "created_at"])
    for q in rows:
        writer.writerow([
            q.question, q.answer, q.top_score, q.response_time_ms,
            q.retrieval_mode, q.fallback_triggered, q.origin_domain,
            q.created_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={site_id}_queries.csv"},
    )


@router.post("/backup/snapshot")
async def trigger_backup_snapshot(
    _: str = Depends(verify_admin_key),
):
    """Trigger an on-demand backup snapshot via Docker."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "compose", "--profile", "backup", "run", "--rm", "zunkiree-backup"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/home/zunkireelabs/devprojects/zunkiree-search-v1",
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={"code": "BACKUP_FAILED", "message": result.stderr[:500]},
            )

        return {"message": "Backup snapshot completed", "output": result.stdout[-500:]}

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail={"code": "BACKUP_TIMEOUT", "message": "Backup timed out after 120s"},
        )


# --- Product Management Endpoints ---

class ProductInfo(BaseModel):
    id: str
    name: str
    price: float | None
    currency: str | None
    brand: str | None
    category: str | None
    in_stock: bool
    url: str | None
    images: list[str] = []


class ProductsListResponse(BaseModel):
    products: list[ProductInfo]
    total: int
    page: int
    page_size: int


class ProductStatsResponse(BaseModel):
    total_products: int
    categories: list[str]
    price_range: dict


@router.get("/products/{site_id}", response_model=ProductsListResponse)
async def list_products(
    site_id: str,
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Paginated list of products for a tenant."""
    customer = await _resolve_customer(site_id, db)

    import json as _json
    base = select(Product).where(Product.customer_id == customer.id)
    count_base = select(func.count()).select_from(Product).where(
        Product.customer_id == customer.id
    )

    if search:
        like = f"%{search}%"
        base = base.where(Product.name.ilike(like))
        count_base = count_base.where(Product.name.ilike(like))

    total = (await db.execute(count_base)).scalar() or 0
    offset = (page - 1) * page_size

    rows = (
        await db.execute(
            base.order_by(Product.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    return ProductsListResponse(
        products=[
            ProductInfo(
                id=str(p.id),
                name=p.name,
                price=p.price,
                currency=p.currency,
                brand=p.brand,
                category=p.category,
                in_stock=p.in_stock,
                url=p.url,
                images=_json.loads(p.images) if p.images else [],
            )
            for p in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/products/{site_id}/{product_id}")
async def delete_product(
    site_id: str,
    product_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Delete a product."""
    customer = await _resolve_customer(site_id, db)

    result = await db.execute(
        delete(Product).where(
            Product.id == uuid.UUID(product_id),
            Product.customer_id == customer.id,
        )
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "Product not found"},
        )

    await db.commit()
    return {"message": "Product deleted successfully"}


@router.get("/products/{site_id}/stats", response_model=ProductStatsResponse)
async def get_product_stats(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Get product statistics for a tenant."""
    customer = await _resolve_customer(site_id, db)

    # Total products
    total_result = await db.execute(
        select(func.count()).select_from(Product).where(
            Product.customer_id == customer.id,
        )
    )
    total = total_result.scalar() or 0

    # Categories
    cat_result = await db.execute(
        select(Product.category).where(
            Product.customer_id == customer.id,
            Product.category.isnot(None),
        ).distinct()
    )
    categories = [row[0] for row in cat_result.fetchall() if row[0]]

    # Price range
    price_result = await db.execute(
        select(
            func.min(Product.price),
            func.max(Product.price),
        ).where(
            Product.customer_id == customer.id,
            Product.price.isnot(None),
        )
    )
    row = price_result.one()
    price_range = {
        "min": float(row[0]) if row[0] is not None else None,
        "max": float(row[1]) if row[1] is not None else None,
    }

    return ProductStatsResponse(
        total_products=total,
        categories=categories,
        price_range=price_range,
    )


@router.post("/products/{site_id}/rescrape")
async def rescrape_products(
    site_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Re-scrape all product pages for a tenant."""
    customer = await _resolve_customer(site_id, db)

    # Get allowed domains
    domains_result = await db.execute(
        select(Domain).where(Domain.customer_id == customer.id)
    )
    domains = [d.domain for d in domains_result.scalars().all()]

    if not domains:
        raise HTTPException(
            status_code=400,
            detail={"code": "NO_DOMAINS", "message": "No domains configured for this customer"},
        )

    from app.services.auto_ingest import run_auto_ingestion
    background_tasks.add_task(run_auto_ingestion, customer.id, customer.site_id, domains)

    return {"message": "Re-scrape queued for all domains"}
