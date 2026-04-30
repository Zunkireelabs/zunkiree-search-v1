"""FastAPI dependencies for Z6's per-tenant admin API.

Two auth zones:
- get_admin_tenant — per-tenant Bearer token + X-Zunkiree-Site-Id header pair
  (SHARED-CONTRACT §12.2). Token is verified against tenant_admin_tokens via
  Argon2id; site_id scope must match. Returns the Customer the token is scoped
  to. Caller errors land as 401 invalid_admin_credentials or 403
  admin_token_scope_mismatch (per §12.7).
- require_master_admin — global X-Admin-Key header for tenant create/delete
  endpoints. Strict-checks settings.master_admin_key; missing env var means the
  surface is disabled (401 master_admin_key_not_configured), distinct from a
  caller mismatch (401 invalid_admin_credentials).

The same Customer-resolution pattern that admin_backend_credentials.py uses
(SELECT by site_id) is reused here so per-tenant routes can rely on the
returned Customer without re-querying.
"""
from __future__ import annotations

import hmac
import logging
from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.customer import Customer
from app.models.tenant_admin_token import TenantAdminToken
from app.services.admin_token_hash import verify_token

logger = logging.getLogger("zunkiree.deps")


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"code": code, "message": message})


def _forbidden(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": code, "message": message})


async def require_master_admin(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> bool:
    """Strict X-Admin-Key check for tenant create/delete (master-only).

    Distinct from admin.py:verify_admin_key — that one validates against
    settings.api_secret_key (the existing dashboard admin key). This one
    validates against settings.master_admin_key, which is a separate env var
    that Stella holds. They are intentionally not the same key: rotating one
    must not affect the other.
    """
    settings = get_settings()
    configured = (settings.master_admin_key or "").strip()
    if not configured:
        # Loud signal: missing env var is operator misconfiguration. Stella
        # sees the same 401 either way, but our logs distinguish the two so a
        # missing key doesn't look like a credential-stuffing probe.
        logger.error(
            "MASTER_ADMIN_KEY not configured; rejecting master admin request"
        )
        raise _unauthorized(
            "master_admin_key_not_configured",
            "Master admin endpoints are disabled (env var missing on this deploy)",
        )

    if not x_admin_key or not hmac.compare_digest(x_admin_key, configured):
        raise _unauthorized(
            "invalid_admin_credentials",
            "Invalid or missing master admin credentials",
        )
    return True


def _parse_bearer(authorization: Optional[str]) -> str:
    """Split 'Bearer <token>' on the first space exactly once. Returns the
    token portion or raises 401."""
    if not authorization:
        raise _unauthorized(
            "invalid_admin_credentials",
            "Missing Authorization header",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized(
            "invalid_admin_credentials",
            "Authorization header must be 'Bearer <token>'",
        )
    return token.strip()


async def get_admin_tenant(
    authorization: Optional[str] = Header(None),
    x_zunkiree_site_id: Optional[str] = Header(None, alias="X-Zunkiree-Site-Id"),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> Customer:
    """Verify per-tenant admin token and return the tenant Customer.

    Steps:
    1. Parse 'Authorization: Bearer zka_sec_<48>'.
    2. Look up active tenant_admin_tokens by secret_prefix (first 8 chars), to
       avoid Argon2id'ing every row in the table on each request.
    3. For each candidate, run Argon2id verify against the stored hash.
    4. Confirm the token's customer.site_id matches X-Zunkiree-Site-Id.
       Mismatch → 403 admin_token_scope_mismatch (token issued for tenant A,
       used to act on tenant B).
    5. Stash the matched token's public id on `request.state.admin_token_id`
       so destructive handlers can attribute audit-log rows to the specific
       token used (Z-Ops hardening sweep).
    6. Update last_used_at fire-and-forget. Errors here do NOT fail the
       request — auditing is best-effort.
    """
    if not x_zunkiree_site_id:
        raise _unauthorized(
            "invalid_admin_credentials",
            "Missing X-Zunkiree-Site-Id header",
        )

    token = _parse_bearer(authorization)
    if len(token) < 8:
        raise _unauthorized(
            "invalid_admin_credentials",
            "Token too short to be valid",
        )
    prefix = token[:8]

    # Active tokens whose stored prefix matches. Most tenants will have 1–2
    # active rows in flight, so this is a tiny candidate set.
    candidates = (
        await db.execute(
            select(TenantAdminToken).where(
                TenantAdminToken.secret_prefix == prefix,
                TenantAdminToken.revoked_at.is_(None),
            )
        )
    ).scalars().all()

    matched: Optional[TenantAdminToken] = None
    for row in candidates:
        if verify_token(token, row.secret_hash):
            matched = row
            break

    if matched is None:
        raise _unauthorized(
            "invalid_admin_credentials",
            "Token not recognised",
        )

    customer = (
        await db.execute(select(Customer).where(Customer.id == matched.customer_id))
    ).scalar_one_or_none()
    if customer is None:
        # Should not happen because of FK CASCADE; treat as auth failure
        # rather than 500 to avoid leaking internal state.
        raise _unauthorized(
            "invalid_admin_credentials",
            "Token not recognised",
        )

    if customer.site_id != x_zunkiree_site_id:
        raise _forbidden(
            "admin_token_scope_mismatch",
            "Token is not scoped to the requested site_id",
        )

    # Stash the public token_id (zka_live_<...>) on request.state so audit-log
    # callers can attribute the action to the specific token used. Skipped when
    # called outside an HTTP request scope (direct unit-test calls).
    if request is not None:
        try:
            request.state.admin_token_id = matched.token_id
        except Exception:
            logger.debug("Failed to stash admin_token_id on request.state", exc_info=True)

    # Best-effort last_used_at update. Swallow exceptions — auditing must
    # never block the request.
    try:
        await db.execute(
            update(TenantAdminToken)
            .where(TenantAdminToken.id == matched.id)
            .values(last_used_at=datetime.utcnow())
        )
        await db.commit()
    except Exception:
        logger.warning("Failed to update last_used_at for admin token", exc_info=True)

    return customer
