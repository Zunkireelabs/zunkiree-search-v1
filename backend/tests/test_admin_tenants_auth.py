"""deps.py auth tests (Z6).

Covers:
- require_master_admin: missing env → 401 master_admin_key_not_configured;
  mismatch → 401 invalid_admin_credentials; match → True.
- get_admin_tenant: valid Bearer + matching site_id → returns Customer;
  site_id mismatch → 403 admin_token_scope_mismatch; missing/invalid token →
  401 invalid_admin_credentials.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps import get_admin_tenant, require_master_admin
from app.services.admin_token_hash import hash_token


@pytest.mark.asyncio
async def test_require_master_admin_missing_env_returns_401_with_distinct_code(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "master_admin_key", "", raising=False)

    with pytest.raises(HTTPException) as exc:
        await require_master_admin(x_admin_key="anything")
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "master_admin_key_not_configured"


@pytest.mark.asyncio
async def test_require_master_admin_mismatch_returns_401_invalid_admin_credentials(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "master_admin_key", "the-real-secret", raising=False)

    with pytest.raises(HTTPException) as exc:
        await require_master_admin(x_admin_key="wrong")
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "invalid_admin_credentials"


@pytest.mark.asyncio
async def test_require_master_admin_missing_header_returns_401(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "master_admin_key", "the-real-secret", raising=False)

    with pytest.raises(HTTPException) as exc:
        await require_master_admin(x_admin_key=None)
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "invalid_admin_credentials"


@pytest.mark.asyncio
async def test_require_master_admin_match_returns_true(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "master_admin_key", "the-real-secret", raising=False)

    assert await require_master_admin(x_admin_key="the-real-secret") is True


# ---------- get_admin_tenant ----------


def _build_token_row(*, customer_id, plaintext: str):
    """Helper: build a MagicMock TenantAdminToken row with the matching
    secret_prefix and a real Argon2id hash of the supplied plaintext."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.customer_id = customer_id
    row.secret_prefix = plaintext[:8]
    row.secret_hash = hash_token(plaintext)
    row.revoked_at = None
    return row


@pytest.mark.asyncio
async def test_get_admin_tenant_returns_customer_on_match():
    customer_id = uuid.uuid4()
    customer = MagicMock()
    customer.id = customer_id
    customer.site_id = "kasa"

    plaintext = "zka_sec_kasaabc123defghi456jklmno789pqrstu012vwxyz03"
    token_row = _build_token_row(customer_id=customer_id, plaintext=plaintext)

    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = [token_row]
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    update_result = MagicMock()  # last_used_at update

    db = AsyncMock()
    db.execute.side_effect = [candidates_result, customer_result, update_result]

    returned = await get_admin_tenant(
        authorization=f"Bearer {plaintext}",
        x_zunkiree_site_id="kasa",
        db=db,
    )
    assert returned is customer


@pytest.mark.asyncio
async def test_get_admin_tenant_site_id_mismatch_returns_403_scope_mismatch():
    """Token issued for tenant A used to act on tenant B → 403, not 401."""
    customer_id = uuid.uuid4()
    customer = MagicMock()
    customer.id = customer_id
    customer.site_id = "kasa"

    plaintext = "zka_sec_kasaabc123defghi456jklmno789pqrstu012vwxyz03"
    token_row = _build_token_row(customer_id=customer_id, plaintext=plaintext)

    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = [token_row]
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer

    db = AsyncMock()
    db.execute.side_effect = [candidates_result, customer_result]

    with pytest.raises(HTTPException) as exc:
        await get_admin_tenant(
            authorization=f"Bearer {plaintext}",
            x_zunkiree_site_id="other-tenant",
            db=db,
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "admin_token_scope_mismatch"


@pytest.mark.asyncio
async def test_get_admin_tenant_missing_authorization_returns_401():
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await get_admin_tenant(authorization=None, x_zunkiree_site_id="kasa", db=db)
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "invalid_admin_credentials"


@pytest.mark.asyncio
async def test_get_admin_tenant_missing_site_id_header_returns_401():
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await get_admin_tenant(
            authorization="Bearer zka_sec_anything_padded_to_realistic_length_for_test_x",
            x_zunkiree_site_id=None,
            db=db,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "invalid_admin_credentials"


@pytest.mark.asyncio
async def test_get_admin_tenant_unknown_token_returns_401():
    """No row matches the prefix → 401, not silent pass-through."""
    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = []  # no candidates

    db = AsyncMock()
    db.execute.side_effect = [candidates_result]

    with pytest.raises(HTTPException) as exc:
        await get_admin_tenant(
            authorization="Bearer zka_sec_unknownsecretpaddedtorealisticlengthxyzzy789",
            x_zunkiree_site_id="kasa",
            db=db,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "invalid_admin_credentials"


@pytest.mark.asyncio
async def test_get_admin_tenant_malformed_bearer_returns_401():
    db = AsyncMock()
    for bad in ("NotBearer xyz", "Bearer ", "xyz", "Bearer"):
        with pytest.raises(HTTPException) as exc:
            await get_admin_tenant(authorization=bad, x_zunkiree_site_id="kasa", db=db)
        assert exc.value.status_code == 401
        assert exc.value.detail["code"] == "invalid_admin_credentials"
