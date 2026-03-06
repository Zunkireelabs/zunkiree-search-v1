import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Customer, UserProfile, QueryLog, WidgetConfig

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
