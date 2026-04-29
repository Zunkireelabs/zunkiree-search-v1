"""Best-effort audit log helper for destructive admin actions (Z-Ops sweep).

Wired into the four destructive admin surfaces (legacy customer DELETE +
api-key rotate, Z6 tenant DELETE + admin-token rotate, chatbot channel
disconnect). Helper failure is logged loudly but never re-raised — the
primary destructive op has already committed, and audit is defense in
depth. Reverse priority (audit-failure-rolls-back-destructive-op) would
turn `admin_audit_log` into a denial-of-service vector.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog
from app.services.correlation import get_correlation_id

logger = logging.getLogger("zunkiree.admin_audit")


def _extract_ip(request: Optional[Request]) -> Optional[str]:
    """Best-effort client IP. Trusts the first hop in X-Forwarded-For; falls
    back to request.client.host. Returns None when no Request context is
    available (e.g., direct unit-test calls)."""
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


def _resolve_actor_for_admin_tenant(request: Optional[Request]) -> str:
    """Map the per-tenant admin Bearer flow to an audit actor string.

    `get_admin_tenant` (deps.py) stashes the matched token's public id on
    `request.state.admin_token_id` after a successful Argon2id match. Read it
    here so per-tenant rotate/etc. can attribute the action to the specific
    token used."""
    token_id = None
    if request is not None:
        token_id = getattr(request.state, "admin_token_id", None)
    return f"tenant_admin:{token_id}" if token_id else "tenant_admin"


async def log_admin_action(
    db: AsyncSession,
    *,
    actor: str,
    action: str,
    target_table: str,
    target_id: Optional[UUID] = None,
    target_site_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """Insert one row in admin_audit_log. Best-effort: any failure is logged
    and swallowed so the primary destructive op (already committed) is not
    rolled back.

    Runs its own commit; do not call from inside a caller transaction that
    needs the audit row to atomically commit with other state.
    """
    try:
        request_id = get_correlation_id()
        ip_address = _extract_ip(request)

        row = AdminAuditLog(
            actor=actor,
            action=action,
            target_table=target_table,
            target_id=target_id,
            target_site_id=target_site_id,
            payload_json=payload or {},
            request_id=request_id,
            ip_address=ip_address,
        )
        db.add(row)
        await db.commit()
    except Exception as exc:  # pragma: no cover - logged below
        logger.error(
            "admin_audit_log insert failed: %s (action=%s site=%s actor=%s)",
            exc, action, target_site_id, actor,
        )
        # Try to leave the session usable for whatever else the handler does.
        try:
            await db.rollback()
        except Exception:
            pass
