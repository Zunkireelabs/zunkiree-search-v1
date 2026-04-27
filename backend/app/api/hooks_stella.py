"""
Inbound webhook endpoint for Stella deliveries (Z4 §3.4.2).

`POST /api/v1/hooks/stella/{site_id}` — auth is entirely via HMAC signature
(SHARED-CONTRACT §7.4). No API key. The receiver:

1. Reads the raw request body BEFORE any JSON parsing — the signature is
   computed over the exact bytes Stella sent. FastAPI's auto-JSON would
   re-serialize and invalidate the signature.
2. Looks up the tenant + their stored webhook signing secret.
3. Verifies HMAC + replay window.
4. Parses the envelope, confirms the merchant.site_id matches our stored
   `remote_site_id` (defense against a mis-routed delivery from another
   tenant being processed under the wrong customer).
5. Idempotently inserts into `inbound_webhook_events` keyed by
   (source, event_id) — duplicate deliveries become no-ops.
6. Returns 200 (background dispatcher picks it up within 5 seconds).

Status discipline (§3.5): signature mismatch returns **401**, never 5xx.
A 5xx on a known-bad request would trigger Stella's retry policy (§7.6)
against a request Stella knows is wrong, polluting both sides' logs.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.database import get_db
from app.models.customer import Customer
from app.models.tenant_backend_credentials import TenantBackendCredentials
from app.services.connectors.encryption import decrypt
from app.services.inbound_event_dispatcher import insert_event_idempotent
from app.services.webhook_signature import verify_signature

logger = logging.getLogger("zunkiree.hooks.stella")

router = APIRouter(prefix="/hooks", tags=["webhooks", "stella"])

SIGNATURE_HEADER = "X-Stella-Signature"


def _safe_uuid(value) -> UUID | None:
    """Return a UUID iff `value` is a uuid-shaped string, else None.

    Stella's correlation_id field is a UUID v4 per SHARED-CONTRACT §5.1, but
    a malformed envelope shouldn't 500 the receiver — we drop the bad value
    and process the event without it. The signature has already been verified
    at this point so the request is authentic; the worst case is missing a
    correlation join across systems for that one event.
    """
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


@router.post("/stella/{site_id}")
async def receive_stella_webhook(
    site_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    raw_body: bytes = await request.body()
    signature_header = request.headers.get(SIGNATURE_HEADER, "")

    # ---- Tenant lookup: site_id → customer → backend creds row ----
    customer = (
        await db.execute(select(Customer).where(Customer.site_id == site_id))
    ).scalar_one_or_none()
    if customer is None:
        # Unknown tenant — 401 (NOT 404). 404 would let an attacker enumerate
        # which site_ids exist in the system; 401 is the same response
        # signature-mismatch would yield for a known tenant.
        logger.info("inbound webhook for unknown site_id=%s", site_id)
        raise HTTPException(status_code=401, detail="invalid_signature")

    creds = (
        await db.execute(
            select(TenantBackendCredentials).where(
                TenantBackendCredentials.customer_id == customer.id,
                TenantBackendCredentials.backend_type == "stella",
                TenantBackendCredentials.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if creds is None or not creds.webhook_signing_secret_encrypted:
        logger.info(
            "inbound webhook arrived for site_id=%s but no webhook signing secret stored",
            site_id,
        )
        raise HTTPException(status_code=401, detail="invalid_signature")

    try:
        signing_secret = decrypt(creds.webhook_signing_secret_encrypted)
    except Exception:
        # Encryption misconfiguration is operator pain, not Stella's fault.
        # Surface as 500 so it's loud in logs; Stella's retry will try again
        # once the operator fixes the env.
        logger.exception("failed to decrypt webhook signing secret for site_id=%s", site_id)
        raise HTTPException(status_code=500, detail="server_misconfigured")

    # ---- Signature verification (constant-time, replay-windowed) ----
    if not verify_signature(signing_secret, raw_body, signature_header):
        # 401 even if the header was malformed — never 5xx for sig issues.
        raise HTTPException(status_code=401, detail="invalid_signature")

    # ---- Envelope parse ----
    try:
        envelope = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        # Past signature, so the bytes ARE Stella's, but they didn't json
        # decode. 400 is correct: Stella shouldn't retry a malformed body.
        logger.warning("inbound webhook body not valid JSON: %s", e)
        raise HTTPException(status_code=400, detail="invalid_request")

    if not isinstance(envelope, dict):
        raise HTTPException(status_code=400, detail="invalid_request")

    event_id = envelope.get("id")
    event_type = envelope.get("event")
    merchant = envelope.get("merchant") or {}
    envelope_site_id = merchant.get("site_id")

    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="invalid_request")

    # Site-id-mismatch is 401 per Z4 brief §3.4 — guards against a mis-routed
    # delivery being processed under the wrong tenant.
    if envelope_site_id and envelope_site_id != creds.remote_site_id:
        logger.warning(
            "inbound webhook merchant.site_id=%s != stored remote_site_id=%s for site=%s",
            envelope_site_id, creds.remote_site_id, site_id,
        )
        raise HTTPException(status_code=401, detail="invalid_signature")

    correlation_id = _safe_uuid(envelope.get("correlation_id"))

    # ---- Idempotent insert (dedup by (source, event_id)) ----
    inserted = await insert_event_idempotent(
        db,
        customer_id=customer.id,
        source="stella",
        event_id=str(event_id),
        event_type=str(event_type),
        payload=envelope,
        correlation_id=correlation_id,
    )

    if inserted:
        logger.info(
            "inbound webhook accepted event_id=%s type=%s site=%s",
            event_id, event_type, site_id,
        )
    else:
        logger.info(
            "inbound webhook deduped event_id=%s type=%s site=%s",
            event_id, event_type, site_id,
        )

    # 200 either way per SHARED-CONTRACT §7.5 at-least-once contract.
    return Response(status_code=200)
