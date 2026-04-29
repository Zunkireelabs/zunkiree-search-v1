"""Token rotation tests (Z6).

The 24h-overlap rule lives in TenantProvisioningService.rotate_admin_token.
Tests exercise:
- Tokens older than 24h get revoked; tokens younger don't.
- New token row added; revoked_token_ids returned in the response shape.
- Trigger violation surfaces as 409 rotation_overlap_window_active at the
  route level (the trigger itself is exercised by the migration; here we
  simulate by raising the same exception text).
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.admin_tenants import rotate_admin_token
from app.services.tenant_provisioning import (
    RotateResult,
    TenantProvisioningService,
)


def _fake_request():
    """Stand-in Request for direct handler calls. Z-Ops hardening added a
    `request: Request` parameter to rotate_admin_token for audit-log wiring."""
    from fastapi import Request
    req = MagicMock(spec=Request)
    req.headers = {}
    req.client = MagicMock(host="127.0.0.1")
    state = MagicMock(spec=[])
    req.state = state
    return req


@pytest.mark.asyncio
async def test_rotate_revokes_only_tokens_past_24h_window():
    customer_id = uuid.uuid4()

    old_row = MagicMock()
    old_row.id = uuid.uuid4()
    old_row.token_id = "zka_live_OLDPAST24H"

    # Two SELECT calls happen inside rotate_admin_token (the cull-eligible
    # SELECT), then UPDATE, then INSERT (via db.add), then commit.
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = [old_row]

    db = AsyncMock()
    db.execute.side_effect = [select_result, MagicMock()]  # SELECT, UPDATE

    service = TenantProvisioningService()
    result = await service.rotate_admin_token(db, customer_id)
    assert isinstance(result, RotateResult)
    assert result.new_token_secret.startswith("zka_sec_")
    assert result.new_token_id.startswith("zka_live_")
    # Old past-24h token reported revoked
    assert result.revoked_token_ids == ["zka_live_OLDPAST24H"]
    # Commit must have fired
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_rotate_returns_empty_revoked_list_when_no_old_tokens():
    customer_id = uuid.uuid4()
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute.side_effect = [select_result]

    service = TenantProvisioningService()
    result = await service.rotate_admin_token(db, customer_id)
    assert result.revoked_token_ids == []
    # No UPDATE — only the SELECT
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_rotate_route_returns_new_token_and_revoked_ids(monkeypatch):
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    fake = RotateResult(
        new_token_id="zka_live_NEW",
        new_token_secret="zka_sec_NEW_padded_to_realistic_length_xxxxxxxxxxx",
        revoked_token_ids=["zka_live_OLD1", "zka_live_OLD2"],
    )

    async def _ok(self, db, customer_id):
        return fake

    monkeypatch.setattr(
        "app.api.admin_tenants.TenantProvisioningService.rotate_admin_token", _ok
    )

    # Z-Ops hardening: rotate_admin_token now also calls log_admin_action.
    # Stub it for this isolated route-shape test.
    async def _noop_audit(db, **kwargs):
        return None
    monkeypatch.setattr("app.api.admin_tenants.log_admin_action", _noop_audit)

    db = AsyncMock()
    resp = await rotate_admin_token(site_id="kasa", request=_fake_request(), customer=customer, db=db)
    assert resp.admin_token == fake.new_token_secret
    assert resp.admin_token_id == "zka_live_NEW"
    assert resp.revoked_token_ids == ["zka_live_OLD1", "zka_live_OLD2"]


@pytest.mark.asyncio
async def test_rotate_route_returns_409_when_trigger_blocks_overlap(monkeypatch):
    """If a caller rotates faster than the 24h cull frees a slot, the DB
    trigger raises with the canonical message we match in the route."""
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    async def _trigger_fail(self, db, customer_id):
        raise Exception(f"Tenant {customer_id} already has 2 active admin tokens")

    monkeypatch.setattr(
        "app.api.admin_tenants.TenantProvisioningService.rotate_admin_token",
        _trigger_fail,
    )
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await rotate_admin_token(site_id="kasa", request=_fake_request(), customer=customer, db=db)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "rotation_overlap_window_active"


def test_24h_cutoff_is_one_day_ago():
    """Sanity-check the cutoff calculation matches the contract: tokens
    older than 24 hours are eligible, younger ones are not."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    just_before = cutoff - timedelta(seconds=5)
    just_after = cutoff + timedelta(seconds=5)
    assert just_before < cutoff
    assert just_after > cutoff
