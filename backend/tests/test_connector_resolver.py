"""
Tests for ConnectorResolver.for_tenant — the dispatching logic that
chooses between v1 (per-tenant credentials row) and legacy (global env var
fallback).

Mocks the AsyncSession to keep these tests pure unit / no DB. Encryption
is real (Fernet) — conftest sets BACKEND_CREDENTIALS_ENCRYPTION_KEY.
"""
import uuid
from unittest.mock import MagicMock, AsyncMock

import pytest

from app.services.connectors.encryption import encrypt
from app.services.connectors.resolver import ConnectorResolver
from app.services.connectors import AgenticomConnector


def _mock_session_returning(*results):
    """Return an AsyncMock AsyncSession whose successive .execute() calls
    return MagicMocks with .scalar_one_or_none() returning each given value.
    """
    db = AsyncMock()
    return_values = []
    for r in results:
        m = MagicMock()
        m.scalar_one_or_none.return_value = r
        return_values.append(m)
    db.execute.side_effect = return_values
    return db


async def test_resolver_returns_v1_connector_when_active_row_with_credentials():
    customer_id = uuid.uuid4()
    encrypted_secret = encrypt("ssk_sec_xyz")

    row = MagicMock()
    row.sync_key_id = "ssk_live_abc"
    row.sync_key_secret_encrypted = encrypted_secret
    row.remote_site_id = "kasa-stella"

    db = _mock_session_returning(row)

    conn = await ConnectorResolver.for_tenant(db, customer_id)

    assert isinstance(conn, AgenticomConnector)
    assert conn.mode == "v1"
    assert conn._sync_key_id == "ssk_live_abc"
    assert conn._sync_key_secret == "ssk_sec_xyz"
    assert conn._remote_site_id == "kasa-stella"
    # Resolver should have stopped after finding the credentials row.
    assert db.execute.call_count == 1


async def test_resolver_falls_back_to_legacy_when_no_row(monkeypatch):
    customer_id = uuid.uuid4()

    # Force settings to provide a legacy secret.
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "agenticom_api_url", "https://example.test", raising=False)
    monkeypatch.setattr(s, "agenticom_sync_secret", "legacy-shared", raising=False)

    # No credentials row, then customer.site_id lookup returns "kasa-legacy".
    db = _mock_session_returning(None, "kasa-legacy")

    conn = await ConnectorResolver.for_tenant(db, customer_id)

    assert isinstance(conn, AgenticomConnector)
    assert conn.mode == "legacy"
    assert conn._legacy_secret == "legacy-shared"
    assert conn._remote_site_id == "kasa-legacy"


async def test_resolver_falls_back_to_legacy_when_row_missing_sync_key(monkeypatch):
    """Defensive: a half-populated row (e.g. only webhook secret set) should
    still route through the legacy path."""
    customer_id = uuid.uuid4()

    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "agenticom_api_url", "https://example.test", raising=False)
    monkeypatch.setattr(s, "agenticom_sync_secret", "legacy-shared", raising=False)

    row = MagicMock()
    row.sync_key_id = None  # half-populated
    row.sync_key_secret_encrypted = None
    row.remote_site_id = "kasa"

    db = _mock_session_returning(row, "kasa-legacy")

    conn = await ConnectorResolver.for_tenant(db, customer_id)
    assert conn.mode == "legacy"
    assert conn._remote_site_id == "kasa-legacy"


async def test_resolver_falls_back_to_legacy_on_decryption_failure(monkeypatch, caplog):
    """If encryption is misconfigured, must NOT break unmigrated traffic.
    Falls back to legacy + logs an error."""
    customer_id = uuid.uuid4()

    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "agenticom_api_url", "https://example.test", raising=False)
    monkeypatch.setattr(s, "agenticom_sync_secret", "legacy-shared", raising=False)

    row = MagicMock()
    row.sync_key_id = "ssk_live_abc"
    row.sync_key_secret_encrypted = "this-is-not-a-valid-fernet-token"
    row.remote_site_id = "kasa"

    db = _mock_session_returning(row, "kasa-legacy")

    import logging
    with caplog.at_level(logging.ERROR):
        conn = await ConnectorResolver.for_tenant(db, customer_id)

    assert conn.mode == "legacy"
    assert any("Failed to decrypt sync key" in r.message for r in caplog.records)
