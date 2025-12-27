import uuid
import secrets
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Customer, Domain, WidgetConfig, IngestionJob
from app.services.ingestion import get_ingestion_service
from app.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


# Authentication dependency
async def verify_admin_key(x_admin_key: str = Header(...)):
    # DEBUG: Log comparison details (not full values)
    print(f"DEBUG verify_admin_key: received key length={len(x_admin_key)}, first 3 chars='{x_admin_key[:3]}...'")
    print(f"DEBUG verify_admin_key: expected key length={len(settings.api_secret_key)}, first 3 chars='{settings.api_secret_key[:3]}...'")
    print(f"DEBUG verify_admin_key: keys match={x_admin_key == settings.api_secret_key}")
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


@router.post("/ingest/document", response_model=JobResponse)
async def ingest_document(
    customer_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin_key),
):
    """Upload and ingest a document (PDF)."""
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

    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_FILE_TYPE", "message": "Only PDF files are supported"},
        )

    ingestion_service = get_ingestion_service()

    try:
        content = await file.read()

        job = await ingestion_service.ingest_pdf(
            db=db,
            customer_id=customer.id,
            site_id=customer.site_id,
            pdf_content=content,
            filename=file.filename,
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
