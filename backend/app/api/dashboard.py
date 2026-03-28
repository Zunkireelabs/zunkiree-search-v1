import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Customer, UserProfile, QueryLog, WidgetConfig, IngestionJob
from app.services.ingestion import get_ingestion_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# --- Authentication: resolve customer by API key ---

async def get_current_customer(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.api_key == x_api_key, Customer.is_active == True)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or inactive API key"},
        )
    return customer


# --- Response models ---

class DashboardOverview(BaseModel):
    site_id: str
    brand_name: str
    total_leads: int
    total_queries: int


class LeadItem(BaseModel):
    id: str
    email: str
    name: str
    phone: str | None
    location: str | None
    user_type: str | None
    lead_intent: str | None
    custom_fields: str | None
    created_at: str


class LeadsResponse(BaseModel):
    leads: list[LeadItem]
    total: int
    page: int
    page_size: int


class QueryItem(BaseModel):
    id: str
    question: str
    answer_preview: str | None
    top_score: float | None
    response_time_ms: int | None
    fallback_triggered: bool
    created_at: str


class QueriesResponse(BaseModel):
    queries: list[QueryItem]
    total: int
    page: int
    page_size: int


# --- Endpoints ---

@router.get("/overview", response_model=DashboardOverview)
async def dashboard_overview(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Get overview stats for the authenticated customer."""
    leads_count = (await db.execute(
        select(func.count()).select_from(UserProfile).where(
            UserProfile.customer_id == customer.id
        )
    )).scalar() or 0

    queries_count = (await db.execute(
        select(func.count()).select_from(QueryLog).where(
            QueryLog.customer_id == customer.id
        )
    )).scalar() or 0

    config = (await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )).scalar_one_or_none()

    return DashboardOverview(
        site_id=customer.site_id,
        brand_name=config.brand_name if config else customer.name,
        total_leads=leads_count,
        total_queries=queries_count,
    )


@router.get("/leads", response_model=LeadsResponse)
async def list_leads(
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Paginated leads list for the authenticated customer."""
    base = select(UserProfile).where(UserProfile.customer_id == customer.id)
    count_q = select(func.count()).select_from(UserProfile).where(
        UserProfile.customer_id == customer.id
    )

    if search:
        like = f"%{search}%"
        base = base.where(
            (UserProfile.email.ilike(like)) | (UserProfile.name.ilike(like))
        )
        count_q = count_q.where(
            (UserProfile.email.ilike(like)) | (UserProfile.name.ilike(like))
        )

    total = (await db.execute(count_q)).scalar() or 0
    offset = (page - 1) * page_size
    rows = (await db.execute(
        base.order_by(UserProfile.created_at.desc()).offset(offset).limit(page_size)
    )).scalars().all()

    return LeadsResponse(
        leads=[
            LeadItem(
                id=str(u.id),
                email=u.email,
                name=u.name,
                phone=u.phone,
                location=u.location,
                user_type=u.user_type,
                lead_intent=u.lead_intent,
                custom_fields=u.custom_fields,
                created_at=u.created_at.isoformat(),
            )
            for u in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/leads/export")
async def export_leads(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """CSV export of all leads."""
    rows = (await db.execute(
        select(UserProfile)
        .where(UserProfile.customer_id == customer.id)
        .order_by(UserProfile.created_at.desc())
    )).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "name", "phone", "location", "user_type", "lead_intent", "custom_fields", "created_at"])
    for u in rows:
        writer.writerow([u.email, u.name, u.phone, u.location, u.user_type, u.lead_intent, u.custom_fields, u.created_at.isoformat()])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={customer.site_id}_leads.csv"},
    )


@router.get("/queries", response_model=QueriesResponse)
async def list_queries(
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Paginated query history for the authenticated customer."""
    base = select(QueryLog).where(QueryLog.customer_id == customer.id)
    count_q = select(func.count()).select_from(QueryLog).where(
        QueryLog.customer_id == customer.id
    )

    if search:
        like = f"%{search}%"
        base = base.where(QueryLog.question.ilike(like))
        count_q = count_q.where(QueryLog.question.ilike(like))

    total = (await db.execute(count_q)).scalar() or 0
    offset = (page - 1) * page_size
    rows = (await db.execute(
        base.order_by(QueryLog.created_at.desc()).offset(offset).limit(page_size)
    )).scalars().all()

    return QueriesResponse(
        queries=[
            QueryItem(
                id=str(q.id),
                question=q.question,
                answer_preview=q.answer[:200] if q.answer else None,
                top_score=round(q.top_score, 3) if q.top_score is not None else None,
                response_time_ms=q.response_time_ms,
                fallback_triggered=q.fallback_triggered,
                created_at=q.created_at.isoformat(),
            )
            for q in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/queries/export")
async def export_queries(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """CSV export of all queries."""
    rows = (await db.execute(
        select(QueryLog)
        .where(QueryLog.customer_id == customer.id)
        .order_by(QueryLog.created_at.desc())
    )).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["question", "answer", "top_score", "response_time_ms", "fallback_triggered", "created_at"])
    for q in rows:
        writer.writerow([
            q.question, q.answer, q.top_score, q.response_time_ms,
            q.fallback_triggered, q.created_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={customer.site_id}_queries.csv"},
    )


# --- Ingestion endpoints ---

class IngestUrlRequest(BaseModel):
    url: str = Field(..., description="URL to crawl")
    max_pages: int = Field(1, ge=1, le=50, description="Maximum pages to crawl")


class QAPair(BaseModel):
    question: str = Field(..., min_length=5)
    answer: str = Field(..., min_length=10)


class IngestQABatchRequest(BaseModel):
    qa_pairs: list[QAPair] = Field(..., min_length=1, max_length=50)


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


@router.post("/ingest/url", response_model=JobResponse)
async def dashboard_ingest_url(
    request: IngestUrlRequest,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Ingest content from a URL (client-facing)."""
    ingestion_service = get_ingestion_service()
    try:
        job = await ingestion_service.ingest_url(
            db=db,
            customer_id=customer.id,
            site_id=customer.site_id,
            url=request.url,
            depth=0,
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


ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx", ".txt": "text"}
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/ingest/file", response_model=JobResponse)
async def dashboard_ingest_file(
    file: UploadFile = File(...),
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Upload and ingest a document (client-facing)."""
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_FILE_TYPE", "message": f"Allowed types: {', '.join(ALLOWED_EXTENSIONS.keys())}"},
        )
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": "Maximum file size is 10MB"},
        )
    ingestion_service = get_ingestion_service()
    try:
        job = await ingestion_service.ingest_file(
            db=db,
            customer_id=customer.id,
            site_id=customer.site_id,
            file_bytes=content,
            filename=filename,
            source_type=ALLOWED_EXTENSIONS[ext],
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


@router.post("/ingest/qa/batch", response_model=dict)
async def dashboard_ingest_qa_batch(
    request: IngestQABatchRequest,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Ingest multiple Q&A pairs (client-facing)."""
    ingestion_service = get_ingestion_service()
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
            if job.status == "completed":
                succeeded += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    return {"total": len(request.qa_pairs), "succeeded": succeeded, "failed": failed}


# --- Widget config endpoints ---

class UpdateConfigRequest(BaseModel):
    brand_name: str | None = None
    tone: str | None = Field(None, pattern="^(formal|neutral|friendly)$")
    primary_color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    welcome_message: str | None = None
    confidence_threshold: float | None = Field(None, ge=0.1, le=0.5)


class WidgetConfigResponse(BaseModel):
    brand_name: str
    tone: str
    primary_color: str
    welcome_message: str | None
    confidence_threshold: float


@router.get("/config", response_model=WidgetConfigResponse)
async def get_dashboard_config(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Get widget config for the authenticated customer."""
    result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        return WidgetConfigResponse(
            brand_name=customer.name,
            tone="neutral",
            primary_color="#2563eb",
            welcome_message=None,
            confidence_threshold=0.25,
        )
    return WidgetConfigResponse(
        brand_name=config.brand_name or customer.name,
        tone=config.tone or "neutral",
        primary_color=config.primary_color or "#2563eb",
        welcome_message=config.welcome_message,
        confidence_threshold=config.confidence_threshold if config.confidence_threshold is not None else 0.25,
    )


@router.put("/config")
async def update_dashboard_config(
    request: UpdateConfigRequest,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """Update widget config for the authenticated customer."""
    result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        config = WidgetConfig(customer_id=customer.id, brand_name=customer.name)
        db.add(config)
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(config, field, value)
    await db.commit()
    return {"message": "Config updated successfully"}


# --- Jobs endpoint ---

@router.get("/jobs", response_model=JobsListResponse)
async def list_dashboard_jobs(
    limit: int = 20,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    """List ingestion jobs for the authenticated customer."""
    result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.customer_id == customer.id)
        .order_by(IngestionJob.created_at.desc())
        .limit(limit)
    )
    jobs = result.scalars().all()
    return JobsListResponse(
        jobs=[
            JobInfo(
                id=str(j.id),
                source_type=j.source_type,
                source_url=j.source_url,
                source_filename=j.source_filename,
                status=j.status,
                chunks_created=j.chunks_created,
                created_at=j.created_at.isoformat(),
                completed_at=j.completed_at.isoformat() if j.completed_at else None,
            )
            for j in jobs
        ],
        total=len(jobs),
    )
