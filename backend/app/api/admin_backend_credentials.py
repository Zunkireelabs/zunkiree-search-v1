"""
Admin endpoints for per-tenant backend credentials.

Auth: existing X-Admin-Key (master admin) via verify_admin_key from admin.py.
Z2 surface only — Stella's per-tenant admin token (zka_sec_*) lands in Task F.

Routes:
- POST   /admin/tenants/{site_id}/backend-credentials       create
- GET    /admin/tenants/{site_id}/backend-credentials       list (no secrets)
- DELETE /admin/tenants/{site_id}/backend-credentials/{id}  delete
- POST   /admin/tenants/{site_id}/backend-credentials/{id}/rotate
                                                            in-place key swap
"""
from datetime import datetime
from typing import Optional
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

router = APIRouter(prefix="/admin", tags=["admin", "backend-credentials"])


# --- Request / response schemas ---

class CreateBackendCredentialsRequest(BaseModel):
    backend_type: str = Field(..., description='Backend identifier, e.g. "stella"')
    remote_site_id: str = Field(..., description="Merchant identifier in the backend system")
    sync_key_id: str = Field(..., description='Public sync key id, e.g. "ssk_live_..."')
    sync_key_secret: str = Field(..., description='Sync key secret, e.g. "ssk_sec_..." — encrypted at rest')
    extra_config: dict = Field(default_factory=dict, description="Backend-specific extra config (Shopify shop domain, etc.)")


class RotateBackendCredentialsRequest(BaseModel):
    sync_key_id: str = Field(..., description="New primary sync key id")
    sync_key_secret: str = Field(..., description="New primary sync key secret — encrypted at rest")


class BackendCredentialsResponse(BaseModel):
    id: str
    customer_id: str
    backend_type: str
    remote_site_id: str
    sync_key_id: Optional[str]
    sync_key_id_standby: Optional[str]
    has_webhook_signing_secret: bool
    extra_config: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime


def _to_response(row: TenantBackendCredentials) -> BackendCredentialsResponse:
    return BackendCredentialsResponse(
        id=str(row.id),
        customer_id=str(row.customer_id),
        backend_type=row.backend_type,
        remote_site_id=row.remote_site_id,
        sync_key_id=row.sync_key_id,
        sync_key_id_standby=row.sync_key_id_standby,
        has_webhook_signing_secret=bool(row.webhook_signing_secret_encrypted),
        extra_config=row.extra_config or {},
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get_customer_by_site_id(db: AsyncSession, site_id: str) -> Customer:
    customer = (
        await db.execute(select(Customer).where(Customer.site_id == site_id))
    ).scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "tenant_not_found", "message": f"No tenant with site_id={site_id}"},
        )
    return customer


# --- Endpoints ---

@router.post(
    "/tenants/{site_id}/backend-credentials",
    response_model=BackendCredentialsResponse,
    status_code=201,
    dependencies=[Depends(verify_admin_key)],
)
async def create_backend_credentials(
    site_id: str,
    body: CreateBackendCredentialsRequest,
    db: AsyncSession = Depends(get_db),
) -> BackendCredentialsResponse:
    customer = await _get_customer_by_site_id(db, site_id)

    existing = (
        await db.execute(
            select(TenantBackendCredentials).where(
                TenantBackendCredentials.customer_id == customer.id,
                TenantBackendCredentials.backend_type == body.backend_type,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "credentials_already_exist",
                "message": f"Tenant {site_id} already has {body.backend_type} credentials. Use rotate or delete first.",
            },
        )

    row = TenantBackendCredentials(
        customer_id=customer.id,
        backend_type=body.backend_type,
        remote_site_id=body.remote_site_id,
        sync_key_id=body.sync_key_id,
        sync_key_secret_encrypted=encrypt(body.sync_key_secret),
        extra_config=body.extra_config or {},
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.get(
    "/tenants/{site_id}/backend-credentials",
    response_model=list[BackendCredentialsResponse],
    dependencies=[Depends(verify_admin_key)],
)
async def list_backend_credentials(
    site_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[BackendCredentialsResponse]:
    customer = await _get_customer_by_site_id(db, site_id)
    rows = (
        await db.execute(
            select(TenantBackendCredentials).where(
                TenantBackendCredentials.customer_id == customer.id,
            )
        )
    ).scalars().all()
    return [_to_response(r) for r in rows]


@router.delete(
    "/tenants/{site_id}/backend-credentials/{credential_id}",
    status_code=204,
    dependencies=[Depends(verify_admin_key)],
)
async def delete_backend_credentials(
    site_id: str,
    credential_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer_by_site_id(db, site_id)
    row = (
        await db.execute(
            select(TenantBackendCredentials).where(
                TenantBackendCredentials.id == credential_id,
                TenantBackendCredentials.customer_id == customer.id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": "credentials_not_found", "message": "No credentials with that id for this tenant"},
        )
    await db.delete(row)
    await db.commit()


@router.post(
    "/tenants/{site_id}/backend-credentials/{credential_id}/rotate",
    response_model=BackendCredentialsResponse,
    dependencies=[Depends(verify_admin_key)],
)
async def rotate_backend_credentials(
    site_id: str,
    credential_id: UUID,
    body: RotateBackendCredentialsRequest,
    db: AsyncSession = Depends(get_db),
) -> BackendCredentialsResponse:
    """In-place rotation: current primary moves to the standby slot
    (overwriting whatever was there), the new key becomes primary. Both keys
    remain present for the 24h overlap window described in
    SHARED-CONTRACT.md §4.4. A subsequent rotate will demote this primary
    in turn, overwriting the now-2-rotations-old standby.
    """
    customer = await _get_customer_by_site_id(db, site_id)
    row = (
        await db.execute(
            select(TenantBackendCredentials).where(
                TenantBackendCredentials.id == credential_id,
                TenantBackendCredentials.customer_id == customer.id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": "credentials_not_found", "message": "No credentials with that id for this tenant"},
        )

    # Demote current primary into standby (overwrites whatever the standby was).
    row.sync_key_id_standby = row.sync_key_id
    row.sync_key_secret_standby_encrypted = row.sync_key_secret_encrypted
    # Promote new key to primary.
    row.sync_key_id = body.sync_key_id
    row.sync_key_secret_encrypted = encrypt(body.sync_key_secret)
    row.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(row)
    return _to_response(row)
