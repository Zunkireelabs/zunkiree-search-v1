"""
Tests for per-tenant backend credentials (Z2):
- Encryption: round-trip + strict-mode behavior when key is missing
- Admin response shape: secret never in serialized response
- Rotate handler: in-place swap (current primary → standby, new → primary)
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.admin_backend_credentials import (
    BackendCredentialsResponse,
    CreateBackendCredentialsRequest,
    RotateBackendCredentialsRequest,
    _to_response,
    rotate_backend_credentials,
)
from app.services.connectors.encryption import (
    BackendCredentialsEncryptionError,
    decrypt,
    encrypt,
)


# ---------- Encryption round-trip ----------

def test_encryption_round_trip_returns_original_plaintext():
    plaintext = "ssk_sec_3f7c1d6a8e2b4d7c9a1e5f8b2c4d6e8a"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext
    assert decrypt(ciphertext) == plaintext


def test_encryption_strict_when_key_missing(monkeypatch):
    """Strict: with key unset, encrypt() / decrypt() raise. Module import never
    touches env, so this only fires at first crypto operation."""
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "backend_credentials_encryption_key", "", raising=False)

    with pytest.raises(BackendCredentialsEncryptionError, match="not configured"):
        encrypt("anything")
    with pytest.raises(BackendCredentialsEncryptionError, match="not configured"):
        decrypt("anything")


def test_encryption_strict_when_key_invalid(monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "backend_credentials_encryption_key", "not-a-valid-fernet-key", raising=False)

    with pytest.raises(BackendCredentialsEncryptionError, match="not a valid Fernet key"):
        encrypt("anything")


# ---------- Response shape: secret never serialized ----------

def test_response_shape_excludes_secret_fields():
    """Serializing _to_response output must not contain any plaintext secret
    nor any *_encrypted field. Only sync_key_id (public), remote_site_id, and
    a boolean has_webhook_signing_secret."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.customer_id = uuid.uuid4()
    row.backend_type = "stella"
    row.remote_site_id = "kasa-stella"
    row.sync_key_id = "ssk_live_abc"
    row.sync_key_id_standby = None
    row.sync_key_secret_encrypted = encrypt("ssk_sec_xyz")  # MUST NOT leak
    row.sync_key_secret_standby_encrypted = None
    row.webhook_signing_secret_encrypted = encrypt("whsec_abc")
    row.extra_config = {}
    row.is_active = True
    row.created_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()

    resp = _to_response(row)
    assert isinstance(resp, BackendCredentialsResponse)
    serialized = resp.model_dump()

    # Public id is fine
    assert serialized["sync_key_id"] == "ssk_live_abc"
    # Secret presence is communicated as a bool, not the value
    assert serialized["has_webhook_signing_secret"] is True

    # No secret material anywhere in the serialized dict
    for key, value in serialized.items():
        if isinstance(value, str):
            assert "ssk_sec_" not in value, f"Plaintext sync key secret leaked into field {key}"
            assert "whsec_" not in value, f"Plaintext webhook secret leaked into field {key}"
        assert not key.endswith("_encrypted"), f"Encrypted field {key} leaked into response shape"
        assert key != "sync_key_secret"
        assert key != "sync_key_secret_standby"
        assert key != "webhook_signing_secret"


# ---------- Rotate handler: in-place swap ----------

async def test_rotate_demotes_primary_to_standby_and_promotes_new():
    """Rotation moves current primary (id+secret) into the standby slot,
    overwriting whatever was there, then writes the new pair as primary.
    Verified by directly invoking the handler with mocked DB."""

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    cred_id = uuid.uuid4()
    row = MagicMock()
    row.id = cred_id
    row.customer_id = customer.id
    row.backend_type = "stella"
    row.remote_site_id = "kasa-stella"
    row.sync_key_id = "ssk_live_OLD"
    row.sync_key_secret_encrypted = encrypt("ssk_sec_OLD_secret")
    row.sync_key_id_standby = "ssk_live_ANCIENT"  # will be overwritten
    row.sync_key_secret_standby_encrypted = encrypt("ssk_sec_ANCIENT")
    row.webhook_signing_secret_encrypted = None
    row.extra_config = {}
    row.is_active = True
    row.created_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()

    # Two .execute() calls happen inside the handler:
    #   1. lookup customer by site_id
    #   2. lookup credentials by id+customer
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    cred_result = MagicMock()
    cred_result.scalar_one_or_none.return_value = row

    db = AsyncMock()
    db.execute.side_effect = [customer_result, cred_result]

    body = RotateBackendCredentialsRequest(
        sync_key_id="ssk_live_NEW",
        sync_key_secret="ssk_sec_NEW_secret",
    )

    resp = await rotate_backend_credentials(
        site_id="kasa",
        credential_id=cred_id,
        body=body,
        db=db,
    )

    # New key is now primary
    assert row.sync_key_id == "ssk_live_NEW"
    assert decrypt(row.sync_key_secret_encrypted) == "ssk_sec_NEW_secret"

    # Previous primary is now in standby (overwriting the ancient one)
    assert row.sync_key_id_standby == "ssk_live_OLD"
    assert decrypt(row.sync_key_secret_standby_encrypted) == "ssk_sec_OLD_secret"

    # Response reports the new public id, no secret
    assert resp.sync_key_id == "ssk_live_NEW"
    assert resp.sync_key_id_standby == "ssk_live_OLD"

    # Commit must have fired
    assert db.commit.await_count == 1


# ---------- Create request validation ----------

def test_create_request_requires_secret():
    """Pydantic must reject a payload missing sync_key_secret."""
    with pytest.raises(Exception):  # pydantic.ValidationError
        CreateBackendCredentialsRequest(
            backend_type="stella",
            remote_site_id="kasa",
            sync_key_id="ssk_live_abc",
        )  # missing sync_key_secret


def test_create_request_round_trip():
    req = CreateBackendCredentialsRequest(
        backend_type="stella",
        remote_site_id="kasa",
        sync_key_id="ssk_live_abc",
        sync_key_secret="ssk_sec_def",
    )
    assert req.backend_type == "stella"
    assert req.sync_key_secret == "ssk_sec_def"
    assert req.extra_config == {}
