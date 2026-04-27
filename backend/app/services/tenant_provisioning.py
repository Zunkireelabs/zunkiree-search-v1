"""TenantProvisioningService — Z6 Task F §3.6.4.

Wraps the multi-step tenant lifecycle (Customer + WidgetConfig + admin token +
optional widget script) so admin_tenants.py routes stay thin. Token rotation
follows SHARED-CONTRACT §12.3: 24h overlap window, max 2 active enforced by
the trigger in migration 034.
"""
from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.customer import Customer
from app.models.tenant_admin_token import TenantAdminToken
from app.models.widget_config import WidgetConfig
from app.services.admin_token_hash import hash_token


# Widget config defaults locked in Z6-BRIEF §3.7. Stella's S10 panel surfaces
# these for editing post-provisioning.
DEFAULT_WIDGET_CONFIG = {
    "tone": "neutral",
    "primary_color": "#2563eb",
    "placeholder_text": "Ask a question...",
    "welcome_message": None,
    "quick_actions": None,        # WidgetConfig stores as JSON string
    "lead_intents": None,
    "confidence_threshold": 0.25,
}


@dataclass
class ProvisionResult:
    customer: Customer
    widget_config: WidgetConfig
    admin_token_id: str           # zka_live_<...>
    admin_token_secret: str       # zka_sec_<...> — caller must return-once
    webhook_signing_secret: str   # whsec_<...> — caller must return-once
    widget_script: Optional[str]


@dataclass
class RotateResult:
    new_token_id: str
    new_token_secret: str         # caller must return-once
    revoked_token_ids: list[str]  # public ids only, never secrets


# ---------------------------------------------------------------------------
# Token + secret generators


def _b32(n_bytes: int) -> str:
    """Lowercase base32 without padding — URL-safe-ish, no ambiguous chars."""
    raw = secrets.token_bytes(n_bytes)
    return base64.b32encode(raw).decode("ascii").rstrip("=").lower()


def generate_admin_token() -> tuple[str, str]:
    """Return (token_id, secret) per SHARED-CONTRACT §12.2.

    token_id  = zka_live_<20 base32>
    secret    = zka_sec_<48 chars>
    """
    token_id = f"zka_live_{_b32(13)[:20]}"
    secret = f"zka_sec_{_b32(30)[:48]}"
    return token_id, secret


def generate_webhook_signing_secret() -> str:
    return f"whsec_{secrets.token_urlsafe(32)}"


def build_widget_script(site_id: str) -> Optional[str]:
    """Compose the embed script. WIDGET_SCRIPT_BASE_URL is set on both VPS
    .env files (prod + stage) — the guard returns None if it ever isn't, so a
    misconfigured deploy yields a null field rather than a broken <script>
    tag at the merchant's site.
    """
    base_url = (get_settings().widget_script_base_url or "").strip()
    if not base_url:
        return None
    return (
        f'<script src="{base_url.rstrip("/")}/zunkiree-widget.iife.js" '
        f'data-site-id="{site_id}" '
        f'data-api-url="https://api.zunkireelabs.com"></script>'
    )


# ---------------------------------------------------------------------------
# Service


class TenantAlreadyExistsError(Exception):
    def __init__(self, site_id: str):
        super().__init__(site_id)
        self.site_id = site_id


class TenantProvisioningService:
    async def provision(
        self,
        db: AsyncSession,
        *,
        site_id: str,
        brand_name: str,
        contact_email: Optional[str],
        website_type: Optional[str],
        stella_merchant_id: Optional[str],
    ) -> ProvisionResult:
        """Idempotent in the sense that a duplicate site_id raises a typed
        error so the route can return 409 tenant_already_exists per §12.7.

        Re-POSTing the same site_id never returns the secret a second time —
        Stella stored it Fernet-encrypted at first creation. The recover path
        is GET /admin/tenants/{site_id} (which returns metadata, not the
        secret) plus POST .../admin-tokens/rotate to mint a fresh one.
        """
        existing = (
            await db.execute(select(Customer).where(Customer.site_id == site_id))
        ).scalar_one_or_none()
        if existing:
            raise TenantAlreadyExistsError(site_id)

        # Customer
        customer_api_key = f"zk_live_{site_id}_{secrets.token_urlsafe(24)}"
        customer = Customer(
            name=brand_name,
            site_id=site_id,
            api_key=customer_api_key,
            website_type=website_type,
            stella_merchant_id=stella_merchant_id,
        )
        db.add(customer)
        await db.flush()  # need customer.id for child rows

        # WidgetConfig — brand_name is NOT NULL with no default, so we must
        # supply it here. contact_email lives on widget_configs (Customer has
        # no such column) per Z6 §1.1 finding.
        widget_config = WidgetConfig(
            customer_id=customer.id,
            brand_name=brand_name,
            tone=DEFAULT_WIDGET_CONFIG["tone"],
            primary_color=DEFAULT_WIDGET_CONFIG["primary_color"],
            placeholder_text=DEFAULT_WIDGET_CONFIG["placeholder_text"],
            welcome_message=DEFAULT_WIDGET_CONFIG["welcome_message"],
            quick_actions=DEFAULT_WIDGET_CONFIG["quick_actions"],
            lead_intents=DEFAULT_WIDGET_CONFIG["lead_intents"],
            confidence_threshold=DEFAULT_WIDGET_CONFIG["confidence_threshold"],
            contact_email=contact_email,
        )
        db.add(widget_config)

        # Admin token — full secret returned once.
        token_id, secret = generate_admin_token()
        admin_token = TenantAdminToken(
            customer_id=customer.id,
            token_id=token_id,
            secret_prefix=secret[:8],
            secret_hash=hash_token(secret),
            description="Initial token issued at tenant provisioning",
        )
        db.add(admin_token)

        # Webhook signing secret — surfaced only at provisioning time;
        # registration of an actual outbound subscription happens via the
        # /webhooks endpoint and gets its own per-subscription secret.
        webhook_signing_secret = generate_webhook_signing_secret()

        await db.commit()
        await db.refresh(customer)
        await db.refresh(widget_config)

        return ProvisionResult(
            customer=customer,
            widget_config=widget_config,
            admin_token_id=token_id,
            admin_token_secret=secret,
            webhook_signing_secret=webhook_signing_secret,
            widget_script=build_widget_script(site_id),
        )

    async def update_widget_config(
        self,
        db: AsyncSession,
        customer_id: UUID,
        fields: dict,
    ) -> WidgetConfig:
        """Partial PATCH — only fields with non-None values land. Caller is
        responsible for serialising JSON-shaped fields (quick_actions,
        lead_intents) into JSON strings, since WidgetConfig stores them as
        Text not JSONB."""
        config = (
            await db.execute(
                select(WidgetConfig).where(WidgetConfig.customer_id == customer_id)
            )
        ).scalar_one_or_none()
        if config is None:
            # Defensive — every Customer should have a WidgetConfig from
            # provision(). If it ever doesn't, create defaults so PATCH
            # doesn't 500.
            customer = (
                await db.execute(select(Customer).where(Customer.id == customer_id))
            ).scalar_one()
            config = WidgetConfig(
                customer_id=customer_id,
                brand_name=customer.name,
            )
            db.add(config)
            await db.flush()

        for key, value in fields.items():
            if value is not None:
                setattr(config, key, value)
        config.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(config)
        return config

    async def rotate_admin_token(
        self, db: AsyncSession, customer_id: UUID
    ) -> RotateResult:
        """24h-overlap rotation per §12.3.

        Steps:
        1. Mark any active tokens older than 24h as revoked. This frees
           trigger headroom (max 2 active) for the new token.
        2. Insert the new token. The trigger raises if there are still 2
           active rows after step 1 (i.e. caller is rotating faster than the
           overlap window allows).
        3. Return the new full secret + the public ids of any tokens we
           revoked in step 1, so Stella can audit-log the operation.
        """
        cutoff = datetime.utcnow() - timedelta(hours=24)
        revoked_rows = (
            await db.execute(
                select(TenantAdminToken).where(
                    TenantAdminToken.customer_id == customer_id,
                    TenantAdminToken.revoked_at.is_(None),
                    TenantAdminToken.created_at < cutoff,
                )
            )
        ).scalars().all()

        revoked_ids: list[str] = []
        if revoked_rows:
            now = datetime.utcnow()
            await db.execute(
                update(TenantAdminToken)
                .where(
                    TenantAdminToken.id.in_([r.id for r in revoked_rows])
                )
                .values(revoked_at=now)
            )
            revoked_ids = [r.token_id for r in revoked_rows]

        token_id, secret = generate_admin_token()
        new_token = TenantAdminToken(
            customer_id=customer_id,
            token_id=token_id,
            secret_prefix=secret[:8],
            secret_hash=hash_token(secret),
            description="Rotated token",
        )
        db.add(new_token)
        await db.commit()

        return RotateResult(
            new_token_id=token_id,
            new_token_secret=secret,
            revoked_token_ids=revoked_ids,
        )
