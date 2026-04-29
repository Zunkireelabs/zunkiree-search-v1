"""Per-tenant admin API for Stella callers (Z6, SHARED-CONTRACT §12).

Endpoint families, in §12 sequence so Stella's S8 admin client can
cross-reference 1:1:

    1. Tenant lifecycle      POST/GET/PATCH/DELETE /admin/tenants[/...]
    2. Widget config         GET/PATCH /admin/tenants/{site_id}/widget-config
    3. Sync credentials      POST /admin/tenants/{site_id}/stella-credentials
    4. Analytics             GET /admin/tenants/{site_id}/analytics
    5. Outbound webhooks     POST/GET/DELETE /admin/tenants/{site_id}/webhooks[/{id}]
    6. Token rotation        POST /admin/tenants/{site_id}/admin-tokens/rotate

Auth zones:
    - Master admin (one global token):  require_master_admin   — POST/DELETE /tenants only
    - Per-tenant admin (zka_sec_<48>):  get_admin_tenant       — every other endpoint

Outbound webhook EMISSION is out of scope for Z6 (lands in Z7). Subscriptions
registered here sit in tenant_outbound_webhooks until the dispatcher wires up.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin_tenant, require_master_admin
from app.database import get_db
from app.models.customer import Customer
from app.models.order import Order
from app.models.query_log import QueryLog
from app.models.tenant_backend_credentials import TenantBackendCredentials
from app.models.tenant_outbound_webhook import TenantOutboundWebhook
from app.models.user_profile import UserProfile
from app.models.widget_config import WidgetConfig
from app.services.connectors.encryption import (
    BackendCredentialsEncryptionError,
    encrypt,
)
from app.services.tenant_provisioning import (
    TenantAlreadyExistsError,
    TenantProvisioningService,
    generate_webhook_signing_secret,
)

logger = logging.getLogger("zunkiree.admin.tenants")

router = APIRouter(prefix="/admin", tags=["admin", "tenants"])

# Allowlist for outbound webhook events per SHARED-CONTRACT §12.5. Reject
# unknown events at registration so Z7's dispatcher doesn't have to filter at
# emission time.
ALLOWED_OUTBOUND_EVENTS: set[str] = {
    "lead.captured",
    "query.logged",
    "order.created.via_widget",
}


# ---------------------------------------------------------------------------
# Schemas


class CreateTenantRequest(BaseModel):
    stella_merchant_id: str = Field(..., description="Stella's merchant identifier; persisted on customers.stella_merchant_id for Z7 webhook envelopes")
    site_id: str = Field(..., pattern="^[a-z0-9-]+$", description="Lowercase, alphanumeric, hyphens only — used in URLs and widget data attribute")
    brand_name: str = Field(..., min_length=1, max_length=255)
    contact_email: Optional[str] = Field(None, max_length=255, description="Persisted on widget_configs.contact_email; used as lead-form fallback contact")
    website_type: Optional[str] = Field(None, max_length=20)
    language: Optional[str] = Field(None, max_length=10, description="ISO code; not persisted in v1, accepted for forward compatibility with §12.4 schema")


class WidgetConfigResponse(BaseModel):
    brand_name: str
    tone: str
    primary_color: str
    placeholder_text: str
    welcome_message: Optional[str]
    quick_actions: Optional[Any]
    lead_intents: Optional[Any]
    confidence_threshold: float
    contact_email: Optional[str]
    contact_phone: Optional[str]


class CreateTenantResponse(BaseModel):
    site_id: str
    customer_id: str
    stella_merchant_id: Optional[str]
    widget_config: WidgetConfigResponse
    widget_script: Optional[str]
    admin_token: str = Field(..., description="zka_sec_<48> — shown ONCE; Stella must Fernet-encrypt at rest immediately")
    admin_token_id: str = Field(..., description="zka_live_<id> — public identifier safe to log")
    webhook_signing_secret: str = Field(..., description="whsec_<...> — Stella's inbound receiver uses this to verify Zunkiree-fired events (Z7); shown ONCE")


class TenantResponse(BaseModel):
    site_id: str
    customer_id: str
    name: str
    stella_merchant_id: Optional[str]
    website_type: Optional[str]
    is_active: bool
    widget_config: WidgetConfigResponse
    created_at: datetime
    updated_at: datetime


class UpdateTenantRequest(BaseModel):
    """PATCH on /tenants/{site_id} accepts the same partial widget-config
    fields as PATCH on /tenants/{site_id}/widget-config — per §12.4 the
    distinction is path-only convenience for Stella's UI."""

    brand_name: Optional[str] = Field(None, min_length=1, max_length=255)
    tone: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    placeholder_text: Optional[str] = Field(None, max_length=255)
    welcome_message: Optional[str] = None
    quick_actions: Optional[list[str]] = None
    lead_intents: Optional[list[Any]] = None
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)


class StellaCredentialsRequest(BaseModel):
    sync_key_id: str = Field(..., description="ssk_live_<...>")
    sync_key_secret: str = Field(..., description="ssk_sec_<...> — Fernet-encrypted at rest")
    agenticom_api_url: Optional[str] = Field(None, description="Per-tenant override of AGENTICOM_API_URL (rare; v1 uses the global)")


class StellaCredentialsResponse(BaseModel):
    credential_id: str
    sync_key_id: Optional[str]
    sync_key_id_standby: Optional[str]
    has_webhook_signing_secret: bool
    updated_at: datetime


class TopQuestion(BaseModel):
    question: str
    count: int


class AnalyticsResponse(BaseModel):
    queries_total: int
    queries_with_answer: int
    leads_captured: int
    orders_via_widget: int
    top_questions: list[TopQuestion]
    response_time_p95: Optional[float]


class RegisterWebhookRequest(BaseModel):
    url: str = Field(..., description="Stella's inbound receiver URL")
    events: list[str] = Field(..., min_length=1, description="Subset of {lead.captured, query.logged, order.created.via_widget}")


class WebhookSubscriptionResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    signing_secret_prefix: str
    signing_secret: Optional[str] = Field(None, description="Full whsec_<...> — present only in the create response, never in list/get")
    created_at: datetime
    revoked_at: Optional[datetime]


class RotateAdminTokenResponse(BaseModel):
    admin_token: str = Field(..., description="zka_sec_<...> — shown ONCE")
    admin_token_id: str
    revoked_token_ids: list[str] = Field(..., description="Public ids of tokens we revoked because they were past the 24h overlap window")


# ---------------------------------------------------------------------------
# Helpers


def _widget_config_to_response(config: WidgetConfig) -> WidgetConfigResponse:
    """JSON-encoded text fields are decoded for the client. quick_actions and
    lead_intents are stored as JSON strings (WidgetConfig predates the JSONB
    migration), so we deserialise here."""
    def _maybe_json(s: Optional[str]) -> Optional[Any]:
        if not s:
            return None
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return s

    return WidgetConfigResponse(
        brand_name=config.brand_name,
        tone=config.tone,
        primary_color=config.primary_color,
        placeholder_text=config.placeholder_text,
        welcome_message=config.welcome_message,
        quick_actions=_maybe_json(config.quick_actions),
        lead_intents=_maybe_json(config.lead_intents),
        confidence_threshold=config.confidence_threshold,
        contact_email=config.contact_email,
        contact_phone=config.contact_phone,
    )


async def _load_widget_config(db: AsyncSession, customer_id: UUID) -> WidgetConfig:
    config = (
        await db.execute(
            select(WidgetConfig).where(WidgetConfig.customer_id == customer_id)
        )
    ).scalar_one_or_none()
    if config is None:
        # Should never happen post-provision — defensive.
        raise HTTPException(
            status_code=500,
            detail={"code": "internal_error", "message": "tenant has no widget_config row"},
        )
    return config


def _serialise_patch_field(key: str, value: Any) -> Any:
    """Two WidgetConfig columns (quick_actions, lead_intents) store JSON as
    Text. PATCH accepts native lists/dicts and we encode here so callers
    don't have to."""
    if value is None:
        return None
    if key in {"quick_actions", "lead_intents"} and not isinstance(value, str):
        return json.dumps(value)
    return value


# ---------------------------------------------------------------------------
# 1. Tenant lifecycle


@router.post(
    "/tenants",
    response_model=CreateTenantResponse,
    status_code=201,
    dependencies=[Depends(require_master_admin)],
)
async def create_tenant(
    body: CreateTenantRequest,
    db: AsyncSession = Depends(get_db),
) -> CreateTenantResponse:
    service = TenantProvisioningService()
    try:
        result = await service.provision(
            db,
            site_id=body.site_id,
            brand_name=body.brand_name,
            contact_email=body.contact_email,
            website_type=body.website_type,
            stella_merchant_id=body.stella_merchant_id,
        )
    except TenantAlreadyExistsError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "tenant_already_exists",
                "message": f"Site id '{e.site_id}' is already taken",
            },
        )

    return CreateTenantResponse(
        site_id=result.customer.site_id,
        customer_id=str(result.customer.id),
        stella_merchant_id=result.customer.stella_merchant_id,
        widget_config=_widget_config_to_response(result.widget_config),
        widget_script=result.widget_script,
        admin_token=result.admin_token_secret,
        admin_token_id=result.admin_token_id,
        webhook_signing_secret=result.webhook_signing_secret,
    )


@router.get("/tenants/{site_id}", response_model=TenantResponse)
async def get_tenant(
    site_id: str,
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    config = await _load_widget_config(db, customer.id)
    return TenantResponse(
        site_id=customer.site_id,
        customer_id=str(customer.id),
        name=customer.name,
        stella_merchant_id=customer.stella_merchant_id,
        website_type=customer.website_type,
        is_active=customer.is_active,
        widget_config=_widget_config_to_response(config),
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


@router.patch("/tenants/{site_id}", response_model=TenantResponse)
async def patch_tenant(
    site_id: str,
    body: UpdateTenantRequest,
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    fields = {
        k: _serialise_patch_field(k, v)
        for k, v in body.model_dump(exclude_unset=True).items()
    }
    service = TenantProvisioningService()
    config = await service.update_widget_config(db, customer.id, fields)
    await db.refresh(customer)
    return TenantResponse(
        site_id=customer.site_id,
        customer_id=str(customer.id),
        name=customer.name,
        stella_merchant_id=customer.stella_merchant_id,
        website_type=customer.website_type,
        is_active=customer.is_active,
        widget_config=_widget_config_to_response(config),
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


@router.delete(
    "/tenants/{site_id}",
    status_code=204,
    dependencies=[Depends(require_master_admin)],
)
async def delete_tenant(
    site_id: str,
    confirm: bool = Query(False, description="Must be true; guard against accidental deletes"),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail={"code": "confirmation_required", "message": "Add ?confirm=true to delete"},
        )
    customer = (
        await db.execute(select(Customer).where(Customer.site_id == site_id))
    ).scalar_one_or_none()
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "tenant_not_found", "message": f"No tenant with site_id={site_id}"},
        )
    # Raw SQL DELETE so DB-level CASCADE handles every related table without
    # SQLAlchemy needing each relation registered. Mirrors admin.py's pattern.
    await db.execute(text("DELETE FROM customers WHERE id = :cid"), {"cid": str(customer.id)})
    await db.commit()


# ---------------------------------------------------------------------------
# 2. Widget config


@router.get("/tenants/{site_id}/widget-config", response_model=WidgetConfigResponse)
async def get_widget_config(
    site_id: str,
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> WidgetConfigResponse:
    config = await _load_widget_config(db, customer.id)
    return _widget_config_to_response(config)


@router.patch("/tenants/{site_id}/widget-config", response_model=WidgetConfigResponse)
async def patch_widget_config(
    site_id: str,
    body: UpdateTenantRequest,
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> WidgetConfigResponse:
    fields = {
        k: _serialise_patch_field(k, v)
        for k, v in body.model_dump(exclude_unset=True).items()
    }
    service = TenantProvisioningService()
    config = await service.update_widget_config(db, customer.id, fields)
    return _widget_config_to_response(config)


# ---------------------------------------------------------------------------
# 3. Sync credentials (Stella tells Zunkiree the new ssk_sec_...)


@router.post(
    "/tenants/{site_id}/stella-credentials",
    response_model=StellaCredentialsResponse,
)
async def push_stella_credentials(
    site_id: str,
    body: StellaCredentialsRequest,
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> StellaCredentialsResponse:
    """Per §12.4 the effect is: update tenant_backend_credentials, demoting
    the current primary to standby. Reuses Z2's encryption helper — does not
    re-implement Fernet."""
    creds = (
        await db.execute(
            select(TenantBackendCredentials).where(
                TenantBackendCredentials.customer_id == customer.id,
                TenantBackendCredentials.backend_type == "stella",
            )
        )
    ).scalar_one_or_none()

    try:
        encrypted_secret = encrypt(body.sync_key_secret)
    except BackendCredentialsEncryptionError as e:
        logger.error("encryption helper unavailable: %s", e)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "service_unavailable",
                "message": "Tenant credential service temporarily unavailable",
            },
        )

    if creds is None:
        # First-time push: create the row outright. Stella may call this
        # before any prior /admin/tenants/{site_id}/backend-credentials POST
        # via the master-key admin surface.
        creds = TenantBackendCredentials(
            customer_id=customer.id,
            backend_type="stella",
            remote_site_id=customer.site_id,
            sync_key_id=body.sync_key_id,
            sync_key_secret_encrypted=encrypted_secret,
            is_active=True,
        )
        db.add(creds)
    else:
        # Demote current primary into standby (overwriting the now-stale
        # standby), promote the new pair into primary. Mirrors Z2
        # rotate-in-place semantics.
        creds.sync_key_id_standby = creds.sync_key_id
        creds.sync_key_secret_standby_encrypted = creds.sync_key_secret_encrypted
        creds.sync_key_id = body.sync_key_id
        creds.sync_key_secret_encrypted = encrypted_secret
        creds.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(creds)
    return StellaCredentialsResponse(
        credential_id=str(creds.id),
        sync_key_id=creds.sync_key_id,
        sync_key_id_standby=creds.sync_key_id_standby,
        has_webhook_signing_secret=bool(creds.webhook_signing_secret_encrypted),
        updated_at=creds.updated_at,
    )


# ---------------------------------------------------------------------------
# 4. Analytics


@router.get("/tenants/{site_id}/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    site_id: str,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsResponse:
    """Default window is the trailing 30 days when from/to aren't supplied —
    matches admin.py's existing analytics conventions so Stella's UI doesn't
    need a special-case for the unconfigured-merchant dashboard."""
    # Z6.2: query_logs / user_profiles / orders.created_at columns are
    # naive `DateTime` (not `DateTime(timezone=True)`). Comparing them to
    # tz-aware Pydantic-parsed datetimes raises:
    #   "can't compare offset-naive and offset-aware datetimes"
    # Normalize to naive UTC at the boundary; columns store naive UTC
    # already, so no semantic shift.
    if from_ is not None and from_.tzinfo is not None:
        from_ = from_.astimezone(timezone.utc).replace(tzinfo=None)
    if to is not None and to.tzinfo is not None:
        to = to.astimezone(timezone.utc).replace(tzinfo=None)

    if to is None:
        to = datetime.utcnow()
    if from_ is None:
        from_ = to - timedelta(days=30)

    # queries_total + queries_with_answer + p95 in one aggregation pass.
    # queries_with_answer = answer present AND not a fallback dispatch.
    agg = (
        await db.execute(
            select(
                func.count().label("total"),
                func.sum(
                    case(
                        (
                            (QueryLog.answer.isnot(None))
                            & (QueryLog.fallback_triggered.is_(False)),
                            1,
                        ),
                        else_=0,
                    )
                ).label("with_answer"),
                func.percentile_cont(0.95)
                .within_group(QueryLog.response_time_ms.asc())
                .label("p95"),
            ).where(
                QueryLog.customer_id == customer.id,
                QueryLog.created_at >= from_,
                QueryLog.created_at <= to,
            )
        )
    ).one()
    queries_total = int(agg.total or 0)
    queries_with_answer = int(agg.with_answer or 0)
    p95_value = float(agg.p95) if agg.p95 is not None else None

    leads_captured = int(
        (
            await db.execute(
                select(func.count()).select_from(UserProfile).where(
                    UserProfile.customer_id == customer.id,
                    UserProfile.created_at >= from_,
                    UserProfile.created_at <= to,
                )
            )
        ).scalar()
        or 0
    )

    orders_via_widget = int(
        (
            await db.execute(
                select(func.count()).select_from(Order).where(
                    Order.customer_id == customer.id,
                    Order.created_at >= from_,
                    Order.created_at <= to,
                )
            )
        ).scalar()
        or 0
    )

    # top_questions: group by normalised question, but return the question as
    # the user originally typed it. MIN(question) over the group is stable
    # and cheaper than FIRST_VALUE/window.
    top_rows = (
        await db.execute(
            select(
                func.lower(func.trim(QueryLog.question)).label("norm"),
                func.min(QueryLog.question).label("display"),
                func.count().label("cnt"),
            )
            .where(
                QueryLog.customer_id == customer.id,
                QueryLog.created_at >= from_,
                QueryLog.created_at <= to,
            )
            .group_by(func.lower(func.trim(QueryLog.question)))
            .order_by(desc("cnt"))
            .limit(10)
        )
    ).all()
    top_questions = [
        TopQuestion(question=row.display, count=int(row.cnt)) for row in top_rows
    ]

    return AnalyticsResponse(
        queries_total=queries_total,
        queries_with_answer=queries_with_answer,
        leads_captured=leads_captured,
        orders_via_widget=orders_via_widget,
        top_questions=top_questions,
        response_time_p95=p95_value,
    )


# ---------------------------------------------------------------------------
# 5. Outbound webhook subscriptions (Zunkiree → Stella; emission lands in Z7)


def _webhook_to_response(
    row: TenantOutboundWebhook, *, include_secret: Optional[str] = None
) -> WebhookSubscriptionResponse:
    return WebhookSubscriptionResponse(
        id=str(row.id),
        url=row.url,
        events=list(row.events or []),
        signing_secret_prefix=row.signing_secret_prefix,
        signing_secret=include_secret,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )


@router.post(
    "/tenants/{site_id}/webhooks",
    response_model=WebhookSubscriptionResponse,
    status_code=201,
)
async def register_webhook(
    site_id: str,
    body: RegisterWebhookRequest,
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> WebhookSubscriptionResponse:
    """Register a Stella receiver for events Zunkiree will fire (Z7).
    events must be a subset of ALLOWED_OUTBOUND_EVENTS — unknown values land
    as 400 invalid_request per SHARED-CONTRACT §12.7 (not FastAPI's default
    422 from a Pydantic validator).
    """
    unknown = sorted(set(body.events) - ALLOWED_OUTBOUND_EVENTS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_request",
                "message": f"unknown event types: {unknown}",
            },
        )
    signing_secret = generate_webhook_signing_secret()
    try:
        signing_secret_encrypted = encrypt(signing_secret)
    except BackendCredentialsEncryptionError as e:
        logger.error("encryption helper unavailable: %s", e)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "service_unavailable",
                "message": "Tenant credential service temporarily unavailable",
            },
        )
    row = TenantOutboundWebhook(
        customer_id=customer.id,
        url=body.url,
        events=list(body.events),
        signing_secret_encrypted=signing_secret_encrypted,
        signing_secret_prefix=signing_secret[:16],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _webhook_to_response(row, include_secret=signing_secret)


@router.get(
    "/tenants/{site_id}/webhooks",
    response_model=list[WebhookSubscriptionResponse],
)
async def list_webhooks(
    site_id: str,
    include_revoked: bool = Query(False),
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookSubscriptionResponse]:
    stmt = select(TenantOutboundWebhook).where(
        TenantOutboundWebhook.customer_id == customer.id,
    )
    if not include_revoked:
        stmt = stmt.where(TenantOutboundWebhook.revoked_at.is_(None))
    rows = (await db.execute(stmt.order_by(TenantOutboundWebhook.created_at.desc()))).scalars().all()
    return [_webhook_to_response(r) for r in rows]


@router.delete(
    "/tenants/{site_id}/webhooks/{webhook_id}",
    status_code=204,
)
async def revoke_webhook(
    site_id: str,
    webhook_id: UUID,
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-revoke: set revoked_at, never DELETE. Past deliveries that used
    this signing secret remain auditable."""
    row = (
        await db.execute(
            select(TenantOutboundWebhook).where(
                TenantOutboundWebhook.id == webhook_id,
                TenantOutboundWebhook.customer_id == customer.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "webhook_not_found", "message": "No webhook subscription with that id for this tenant"},
        )
    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        await db.commit()


# ---------------------------------------------------------------------------
# 6. Token rotation


@router.post(
    "/tenants/{site_id}/admin-tokens/rotate",
    response_model=RotateAdminTokenResponse,
)
async def rotate_admin_token(
    site_id: str,
    customer: Customer = Depends(get_admin_tenant),
    db: AsyncSession = Depends(get_db),
) -> RotateAdminTokenResponse:
    service = TenantProvisioningService()
    try:
        result = await service.rotate_admin_token(db, customer.id)
    except Exception as e:
        # The trigger raises if there are still 2 active tokens after the
        # 24h cull. Surface as 409 so Stella can backoff and retry after the
        # overlap window.
        msg = str(e)
        if "already has 2 active admin tokens" in msg:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rotation_overlap_window_active",
                    "message": "Tenant already has 2 active tokens; wait for the 24h overlap window to close before rotating again",
                },
            )
        logger.exception("Admin token rotation failed for site_id=%s", site_id)
        raise

    return RotateAdminTokenResponse(
        admin_token=result.new_token_secret,
        admin_token_id=result.new_token_id,
        revoked_token_ids=result.revoked_token_ids,
    )
