"""Outbound webhook subscription endpoints (Z6).

Z6 only registers/manages subscriptions; emission is Z7. Verified:
- register_webhook stores a row, returns full signing secret ONCE.
- Event allowlist enforced — unknown events → 400 invalid_request (NOT 422).
- list_webhooks filters revoked rows by default; include_revoked=true returns
  all.
- revoke_webhook is a soft revoke (sets revoked_at), never hard-delete, so
  past deliveries' signatures stay auditable.
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.admin_tenants import (
    ALLOWED_OUTBOUND_EVENTS,
    RegisterWebhookRequest,
    list_webhooks,
    register_webhook,
    revoke_webhook,
)
from app.services.connectors.encryption import decrypt


def test_allowlist_matches_shared_contract():
    """Locked set per SHARED-CONTRACT §12.5."""
    assert ALLOWED_OUTBOUND_EVENTS == {
        "lead.captured",
        "query.logged",
        "order.created.via_widget",
    }


@pytest.mark.asyncio
async def test_register_creates_row_and_returns_secret_once():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    added: list = []

    db = AsyncMock()
    # AsyncSession.add is sync in SQLAlchemy 2.x; AsyncMock would make it
    # async and silently swallow the side_effect. Override with MagicMock.
    db.add = MagicMock(side_effect=added.append)

    async def _refresh(row):
        row.id = uuid.uuid4()
        row.created_at = datetime.utcnow()

    db.refresh.side_effect = _refresh

    body = RegisterWebhookRequest(
        url="https://stella.example/inbound/zunkiree",
        events=["lead.captured", "order.created.via_widget"],
    )
    resp = await register_webhook(
        site_id="kasa", body=body, customer=customer, db=db
    )

    assert len(added) == 1
    row = added[0]
    assert row.customer_id == customer.id
    assert row.url == body.url
    assert row.events == ["lead.captured", "order.created.via_widget"]
    # Plaintext secret returned in response, encrypted on the row
    assert resp.signing_secret and resp.signing_secret.startswith("whsec_")
    assert decrypt(row.signing_secret_encrypted) == resp.signing_secret
    # Prefix kept for log-safe identification
    assert row.signing_secret_prefix == resp.signing_secret[:16]
    assert resp.signing_secret_prefix == row.signing_secret_prefix
    assert resp.events == ["lead.captured", "order.created.via_widget"]
    assert resp.revoked_at is None


@pytest.mark.asyncio
async def test_register_rejects_unknown_event_with_400_invalid_request():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    db = AsyncMock()

    body = RegisterWebhookRequest(
        url="https://stella.example/inbound/zunkiree",
        events=["lead.captured", "totally.bogus", "another.bad"],
    )
    with pytest.raises(HTTPException) as exc:
        await register_webhook(site_id="kasa", body=body, customer=customer, db=db)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "invalid_request"
    assert "another.bad" in exc.value.detail["message"]
    assert "totally.bogus" in exc.value.detail["message"]
    # No row was added — validation runs before db.add
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_register_rejects_empty_events_via_pydantic():
    """min_length=1 on events; Pydantic rejects empty list at construction
    time — never reaches the route."""
    with pytest.raises(Exception):
        RegisterWebhookRequest(url="https://x.example", events=[])


@pytest.mark.asyncio
async def test_list_filters_revoked_by_default():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    active = MagicMock()
    active.id = uuid.uuid4()
    active.url = "https://x.example/active"
    active.events = ["lead.captured"]
    active.signing_secret_prefix = "whsec_active_"
    active.created_at = datetime.utcnow()
    active.revoked_at = None

    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [active]

    db = AsyncMock()
    db.execute.return_value = rows_result

    resp = await list_webhooks(
        site_id="kasa", include_revoked=False, customer=customer, db=db
    )
    assert len(resp) == 1
    assert resp[0].url == "https://x.example/active"
    assert resp[0].signing_secret is None  # never include in list responses


@pytest.mark.asyncio
async def test_list_include_revoked_returns_all():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    active = MagicMock()
    active.id = uuid.uuid4()
    active.url = "https://x.example/active"
    active.events = ["lead.captured"]
    active.signing_secret_prefix = "whsec_active_"
    active.created_at = datetime.utcnow()
    active.revoked_at = None

    revoked = MagicMock()
    revoked.id = uuid.uuid4()
    revoked.url = "https://x.example/old"
    revoked.events = ["query.logged"]
    revoked.signing_secret_prefix = "whsec_revoked"
    revoked.created_at = datetime.utcnow()
    revoked.revoked_at = datetime.utcnow()

    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [active, revoked]

    db = AsyncMock()
    db.execute.return_value = rows_result

    resp = await list_webhooks(
        site_id="kasa", include_revoked=True, customer=customer, db=db
    )
    assert len(resp) == 2
    assert {r.url for r in resp} == {"https://x.example/active", "https://x.example/old"}


@pytest.mark.asyncio
async def test_revoke_is_soft_sets_revoked_at_does_not_delete():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    row = MagicMock()
    row.id = uuid.uuid4()
    row.customer_id = customer.id
    row.revoked_at = None

    row_lookup = MagicMock()
    row_lookup.scalar_one_or_none.return_value = row

    db = AsyncMock()
    db.execute.return_value = row_lookup

    await revoke_webhook(
        site_id="kasa", webhook_id=row.id, customer=customer, db=db
    )
    # Soft-revoke: revoked_at stamped, no db.delete call
    assert row.revoked_at is not None
    db.delete.assert_not_called()
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_revoke_already_revoked_is_noop():
    """If the row's already revoked, don't update or commit again."""
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    row = MagicMock()
    row.id = uuid.uuid4()
    row.customer_id = customer.id
    earlier = datetime.utcnow()
    row.revoked_at = earlier

    row_lookup = MagicMock()
    row_lookup.scalar_one_or_none.return_value = row

    db = AsyncMock()
    db.execute.return_value = row_lookup

    await revoke_webhook(
        site_id="kasa", webhook_id=row.id, customer=customer, db=db
    )
    # revoked_at must not be overwritten
    assert row.revoked_at == earlier
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_404_when_missing():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    row_lookup = MagicMock()
    row_lookup.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = row_lookup

    with pytest.raises(HTTPException) as exc:
        await revoke_webhook(
            site_id="kasa", webhook_id=uuid.uuid4(), customer=customer, db=db
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "webhook_not_found"
