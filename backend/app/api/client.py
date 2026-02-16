import uuid

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Customer, WidgetConfig, IngestionJob
from app.services.auth import verify_password, create_access_token, decode_access_token
from app.services.ingestion import get_ingestion_service
from app.config import get_settings

router = APIRouter(prefix="/client", tags=["client"])
settings = get_settings()


# --- Auth dependency ---

async def get_current_customer(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    customer_id = payload.get("sub")
    if not customer_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(
        select(Customer).where(Customer.id == uuid.UUID(customer_id))
    )
    customer = result.scalar_one_or_none()

    if not customer or not customer.is_active:
        raise HTTPException(status_code=401, detail="Customer not found or inactive")

    return customer


# --- Request/Response models ---

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    customer: dict


class ProfileResponse(BaseModel):
    id: str
    name: str
    site_id: str
    email: str | None
    created_at: str


class ClientIngestUrlRequest(BaseModel):
    url: str = Field(..., description="URL to crawl")
    depth: int = Field(0, ge=0, le=2, description="Crawl depth")
    max_pages: int = Field(1, ge=1, le=50, description="Maximum pages to crawl")


class ClientIngestTextRequest(BaseModel):
    text: str = Field(..., min_length=10, description="Text content to ingest")
    title: str = Field("Uploaded Content", description="Title for the content")


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str


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


class UpdateConfigRequest(BaseModel):
    brand_name: str | None = None
    tone: str | None = Field(None, pattern="^(formal|neutral|friendly)$")
    primary_color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    placeholder_text: str | None = None
    welcome_message: str | None = None
    fallback_message: str | None = None
    show_sources: bool | None = None
    show_suggestions: bool | None = None


class ConfigResponse(BaseModel):
    brand_name: str | None
    tone: str | None
    primary_color: str | None
    placeholder_text: str | None
    welcome_message: str | None
    fallback_message: str | None
    show_sources: bool | None
    show_suggestions: bool | None


# --- Endpoints ---

@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Customer login with email and password."""
    result = await db.execute(
        select(Customer).where(Customer.email == request.email)
    )
    customer = result.scalar_one_or_none()

    if not customer or not customer.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(request.password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not customer.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    token = create_access_token(str(customer.id), customer.site_id)

    return LoginResponse(
        token=token,
        customer={
            "id": str(customer.id),
            "name": customer.name,
            "site_id": customer.site_id,
            "email": customer.email,
        },
    )


@router.get("/me", response_model=ProfileResponse)
async def get_profile(
    customer: Customer = Depends(get_current_customer),
):
    """Get current customer profile."""
    return ProfileResponse(
        id=str(customer.id),
        name=customer.name,
        site_id=customer.site_id,
        email=customer.email,
        created_at=customer.created_at.isoformat(),
    )


@router.post("/ingest/url", response_model=JobResponse)
async def ingest_url(
    request: ClientIngestUrlRequest,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Ingest content from a URL (scoped to current customer)."""
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
    request: ClientIngestTextRequest,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Ingest raw text content (scoped to current customer)."""
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


@router.get("/jobs", response_model=JobsListResponse)
async def list_jobs(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """List ingestion jobs for the current customer."""
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


@router.get("/config", response_model=ConfigResponse)
async def get_config(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Get widget configuration for the current customer."""
    result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )
    config = result.scalar_one_or_none()

    if not config:
        return ConfigResponse(
            brand_name=customer.name,
            tone="neutral",
            primary_color="#2563eb",
            placeholder_text=None,
            welcome_message=None,
            fallback_message=None,
            show_sources=True,
            show_suggestions=True,
        )

    return ConfigResponse(
        brand_name=config.brand_name,
        tone=config.tone,
        primary_color=config.primary_color,
        placeholder_text=config.placeholder_text,
        welcome_message=config.welcome_message,
        fallback_message=config.fallback_message,
        show_sources=config.show_sources,
        show_suggestions=config.show_suggestions,
    )


@router.put("/config", response_model=ConfigResponse)
async def update_config(
    request: UpdateConfigRequest,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Update widget configuration for the current customer."""
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

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(config, field, value)

    await db.commit()
    await db.refresh(config)

    return ConfigResponse(
        brand_name=config.brand_name,
        tone=config.tone,
        primary_color=config.primary_color,
        placeholder_text=config.placeholder_text,
        welcome_message=config.welcome_message,
        fallback_message=config.fallback_message,
        show_sources=config.show_sources,
        show_suggestions=config.show_suggestions,
    )


@router.get("/embed-code")
async def get_embed_code(
    customer: Customer = Depends(get_current_customer),
):
    """Get the embed code snippet for the current customer."""
    snippet = (
        f'<script\n'
        f'  src="https://zunkiree-search-v1.vercel.app/zunkiree-widget.iife.js"\n'
        f'  data-site-id="{customer.site_id}"\n'
        f'  data-api-url="https://api.zunkireelabs.com"\n'
        f'></script>'
    )
    return {"embed_code": snippet, "site_id": customer.site_id}
