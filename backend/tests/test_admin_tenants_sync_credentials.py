"""POST /admin/tenants/{site_id}/stella-credentials handler (Z6).

Two modes:
- First-time push: no existing tenant_backend_credentials row → create one.
- Subsequent push: row exists → demote primary to standby, promote new pair.

Verifies the existing Z2 encryption helper is reused — secret never lands
in plaintext on the row.
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.admin_tenants import (
    StellaCredentialsRequest,
    push_stella_credentials,
)
from app.services.connectors.encryption import decrypt, encrypt


@pytest.mark.asyncio
async def test_push_creates_row_when_none_exists():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    creds_lookup = MagicMock()
    creds_lookup.scalar_one_or_none.return_value = None  # no existing row

    db = AsyncMock()
    db.execute.return_value = creds_lookup

    # Capture the row added via db.add
    added: list = []
    db.add.side_effect = added.append

    # db.refresh is awaited; populate fields the response needs
    async def _refresh(row):
        row.id = uuid.uuid4()
        row.updated_at = datetime.utcnow()

    db.refresh.side_effect = _refresh

    body = StellaCredentialsRequest(
        sync_key_id="ssk_live_NEW",
        sync_key_secret="ssk_sec_NEW_padded_to_realistic_length_xx",
    )
    resp = await push_stella_credentials(
        site_id="kasa", body=body, customer=customer, db=db
    )

    assert resp.sync_key_id == "ssk_live_NEW"
    assert resp.sync_key_id_standby is None
    assert resp.has_webhook_signing_secret is False
    assert len(added) == 1
    new_row = added[0]
    assert new_row.backend_type == "stella"
    assert new_row.remote_site_id == customer.site_id
    assert new_row.sync_key_id == "ssk_live_NEW"
    # Plaintext never survives — only the Fernet ciphertext lands
    assert new_row.sync_key_secret_encrypted != "ssk_sec_NEW_padded_to_realistic_length_xx"
    assert decrypt(new_row.sync_key_secret_encrypted) == "ssk_sec_NEW_padded_to_realistic_length_xx"


@pytest.mark.asyncio
async def test_push_rotates_existing_row_in_place():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.customer_id = customer.id
    existing.backend_type = "stella"
    existing.sync_key_id = "ssk_live_OLD"
    existing.sync_key_secret_encrypted = encrypt("ssk_sec_OLD_padded_to_realistic_length_xx")
    existing.sync_key_id_standby = "ssk_live_ANCIENT"
    existing.sync_key_secret_standby_encrypted = encrypt("ssk_sec_ANCIENT_padded_xxxxxxxxxxxxxxxxxx")
    existing.webhook_signing_secret_encrypted = encrypt("whsec_existing_xxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    existing.updated_at = datetime.utcnow()

    creds_lookup = MagicMock()
    creds_lookup.scalar_one_or_none.return_value = existing

    db = AsyncMock()
    db.execute.return_value = creds_lookup

    async def _refresh(row):
        row.updated_at = datetime.utcnow()

    db.refresh.side_effect = _refresh

    body = StellaCredentialsRequest(
        sync_key_id="ssk_live_NEW",
        sync_key_secret="ssk_sec_NEW_padded_to_realistic_length_xx",
    )
    resp = await push_stella_credentials(
        site_id="kasa", body=body, customer=customer, db=db
    )

    # Primary now holds the new pair
    assert existing.sync_key_id == "ssk_live_NEW"
    assert decrypt(existing.sync_key_secret_encrypted) == "ssk_sec_NEW_padded_to_realistic_length_xx"
    # Standby now holds the previous primary (overwriting the ancient pair)
    assert existing.sync_key_id_standby == "ssk_live_OLD"
    assert decrypt(existing.sync_key_secret_standby_encrypted) == "ssk_sec_OLD_padded_to_realistic_length_xx"
    # Existing webhook signing secret untouched
    assert decrypt(existing.webhook_signing_secret_encrypted) == "whsec_existing_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    assert resp.sync_key_id == "ssk_live_NEW"
    assert resp.sync_key_id_standby == "ssk_live_OLD"
    assert resp.has_webhook_signing_secret is True
    assert db.commit.await_count == 1
