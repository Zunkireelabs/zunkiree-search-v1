"""
Admin endpoint to register an inbound webhook subscription on Stella for a
tenant (Z4 §1.4 lock — Option A).

Sibling to admin_backend_credentials.py — same X-Admin-Key auth via
`verify_admin_key`, same site_id-as-path-param style. This endpoint:

1. Loads the tenant's existing per-tenant credentials row (created by
   admin_backend_credentials.py).
2. Resolves a v1-mode connector for that tenant (sync_key_id + secret).
3. Calls connector.register_webhook(url, events) → Stella stores the
   subscription, mints a `whsec_...` signing secret, and returns
   `{id: "whk_...", signing_secret, ...}`.
4. Persists the encrypted secret + a public-safe prefix + the registration
   id back onto the credentials row.

After this call, the tenant is end-to-end ready: Stella will fire signed
deliveries to `POST /api/v1/hooks/stella/{site_id}` and the receiver in
hooks_stella.py can verify them using the secret stored here.
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import verify_admin_key
from app.database import get_db
from app.models.customer import Customer
from app.models.tenant_backend_credentials import TenantBackendCredentials
from app.services.connectors.encryption import encrypt
from app.services.connectors.resolver import ConnectorResolver

logger = logging.getLogger("zunkiree.admin.inbound_webhooks")

router = APIRouter(prefix="/admin", tags=["admin", "inbound-webhooks"])


DEFAULT_EVENTS = [
    "product.created",
    "product.updated",
    "product.deleted",
    "variant.created",
    "variant.updated",
    "variant.deleted",
    "inventory.changed",
    "inventory.low",
    "order.status_changed",
    "order.payment_status_changed",
    "order.fulfillment_status_changed",
]


class RegisterWebhookRequest(BaseModel):
    webhook_url_base: str = Field(
        ...,
        description=(
            "Public URL of this Zunkiree deployment, e.g. "
            "'https://api.zunkireelabs.com' (stage uses the same host; "
            "site_id makes the path tenant-specific). The receiver path "
            "'/api/v1/hooks/stella/{site_id}' is appended automatically."
        ),
    )
    events: list[str] = Field(
        default_factory=lambda: list(DEFAULT_EVENTS),
        description="Stella event types to subscribe to. Defaults to the full v1 set minus order.created (Zunkiree creates those itself).",
    )


class RegisterWebhookResponse(BaseModel):
    credential_id: str
    site_id: str
    webhook_id: str | None
    webhook_signing_secret_prefix: str | None
    events: list[str]
    registered_url: str


@router.post(
    "/tenants/{site_id}/backend-credentials/{credential_id}/register-webhook",
    response_model=RegisterWebhookResponse,
    dependencies=[Depends(verify_admin_key)],
)
async def register_inbound_webhook(
    site_id: str,
    credential_id: UUID,
    body: RegisterWebhookRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterWebhookResponse:
    customer = (
        await db.execute(select(Customer).where(Customer.site_id == site_id))
    ).scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "tenant_not_found", "message": f"No tenant with site_id={site_id}"},
        )

    creds = (
        await db.execute(
            select(TenantBackendCredentials).where(
                TenantBackendCredentials.id == credential_id,
                TenantBackendCredentials.customer_id == customer.id,
            )
        )
    ).scalar_one_or_none()
    if not creds:
        raise HTTPException(
            status_code=404,
            detail={"code": "credentials_not_found", "message": "No credentials with that id for this tenant"},
        )

    if not (creds.sync_key_id and creds.sync_key_secret_encrypted):
        # Cannot register a webhook without v1 sync credentials — Stella's
        # POST /api/sync/v1/webhooks requires Bearer auth (SHARED-CONTRACT §4.2).
        raise HTTPException(
            status_code=409,
            detail={
                "code": "sync_credentials_missing",
                "message": "Tenant has no v1 sync credentials; create them first via /backend-credentials.",
            },
        )

    # Compose the receiver URL deterministically so an operator typo can't
    # send Stella's deliveries to the wrong tenant. Trailing slash trim keeps
    # the joined URL clean.
    base = body.webhook_url_base.rstrip("/")
    target_url = f"{base}/api/v1/hooks/stella/{site_id}"

    connector = await ConnectorResolver.for_tenant(db, customer.id, "stella")

    try:
        result = await connector.register_webhook(target_url, body.events)
    except NotImplementedError as e:
        # Should not happen because we already gated on sync_key_id presence,
        # but keep the surface explicit so an unsupported connector returns 422
        # instead of 500.
        raise HTTPException(status_code=422, detail={"code": "unsupported_connector", "message": str(e)})
    except Exception as e:
        logger.exception("Stella register_webhook failed for site_id=%s", site_id)
        raise HTTPException(status_code=502, detail={"code": "upstream_error", "message": str(e)})

    signing_secret = result.get("signing_secret")
    webhook_id = result.get("id")
    if not signing_secret:
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_invalid", "message": "Stella response missing signing_secret"},
        )

    # Public-safe prefix for log diagnostics — first 12 chars of the secret
    # (e.g. "whsec_abc123") is enough to identify which registration a
    # delivery belongs to without leaking the full secret.
    prefix = signing_secret[:12]

    creds.webhook_signing_secret_encrypted = encrypt(signing_secret)
    creds.webhook_signing_secret_prefix = prefix
    creds.webhook_id = str(webhook_id) if webhook_id else None
    creds.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(creds)

    return RegisterWebhookResponse(
        credential_id=str(creds.id),
        site_id=site_id,
        webhook_id=creds.webhook_id,
        webhook_signing_secret_prefix=creds.webhook_signing_secret_prefix,
        events=list(body.events),
        registered_url=target_url,
    )
