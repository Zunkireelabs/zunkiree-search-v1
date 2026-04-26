"""
Resolve a configured BackendConnector for a given tenant.

Order of precedence:
1. Per-tenant credentials row (`tenant_backend_credentials`) — issues a
   v1-mode connector with Bearer auth.
2. Legacy fallback — global `AGENTICOM_*` env vars + the customer's
   `site_id` as `remote_site_id`. Returns a legacy-mode connector.

The fallback path is **not optional**. Tenants that haven't been migrated to
per-tenant keys must continue to work unchanged — that's the zero-downtime
contract. The resolver biases toward legacy fallback on any ambiguity (no
row, inactive row, missing key fields), never raises for "credentials not
found".
"""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.customer import Customer
from app.models.tenant_backend_credentials import TenantBackendCredentials
from app.services.connectors import BackendConnector, get_connector
from app.services.connectors.encryption import decrypt

logger = logging.getLogger("zunkiree.connectors.resolver")


class ConnectorResolver:
    @staticmethod
    async def for_tenant(
        db: AsyncSession,
        customer_id: UUID,
        backend_type: str = "stella",
    ) -> BackendConnector:
        settings = get_settings()

        row: Optional[TenantBackendCredentials] = (
            await db.execute(
                select(TenantBackendCredentials).where(
                    TenantBackendCredentials.customer_id == customer_id,
                    TenantBackendCredentials.backend_type == backend_type,
                    TenantBackendCredentials.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()

        if row and row.sync_key_id and row.sync_key_secret_encrypted:
            try:
                sync_key_secret = decrypt(row.sync_key_secret_encrypted)
            except Exception as e:
                # Don't break unmigrated-tenant traffic if encryption is misconfigured.
                # Fall back to legacy and log loudly.
                logger.error(
                    "[RESOLVER] Failed to decrypt sync key for customer %s; falling back to legacy: %s",
                    customer_id,
                    e,
                )
            else:
                return get_connector(
                    backend_type,
                    {
                        "api_url": settings.agenticom_api_url,
                        "sync_key_id": row.sync_key_id,
                        "sync_key_secret": sync_key_secret,
                        "remote_site_id": row.remote_site_id,
                    },
                )

        # Legacy fallback — uses Customer.site_id as the remote site identifier.
        site_id = (
            await db.execute(select(Customer.site_id).where(Customer.id == customer_id))
        ).scalar_one_or_none() or ""

        return get_connector(
            backend_type,
            {
                "api_url": settings.agenticom_api_url,
                "legacy_shared_secret": settings.agenticom_sync_secret,
                "remote_site_id": site_id,
            },
        )
