"""Tests for `PATCH /admin/chatbot/channels/{id}` (SBAL-Z0) — update a
channel's token / active flag / name / config in place, without the
soft-delete + re-POST dance that 409s on the (platform, platform_page_id)
duplicate check, and without losing conversation history.

Also covers the `POST /channels` additions (`config`, `is_active`) needed so
a connect no longer requires a follow-up DB write to set
`config.facebook_page_id` ([[zunkiree_chatbot_admin_gotchas]]).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request

from app.services.meta_messaging import decrypt_token, encrypt_token


def _fake_request() -> Request:
    req = MagicMock(spec=Request)
    req.headers = {}
    req.client = MagicMock(host="127.0.0.1")
    state = MagicMock()
    state.admin_token_id = None
    req.state = state
    return req


def _make_channel(**overrides):
    channel = MagicMock()
    channel.id = overrides.get("id", uuid.uuid4())
    channel.customer_id = overrides.get("customer_id", uuid.uuid4())
    channel.platform = overrides.get("platform", "instagram")
    channel.platform_page_id = overrides.get("platform_page_id", "17841400000000")
    channel.page_access_token = overrides.get("page_access_token", "encrypted-old-token")
    channel.channel_name = overrides.get("channel_name", "@kasa_clothing")
    channel.config = overrides.get("config", {"abbreviations": {"pp": "price please"}})
    channel.is_active = overrides.get("is_active", True)
    channel.created_at = overrides.get("created_at", __import__("datetime").datetime(2026, 1, 1))
    return channel


@pytest.fixture(autouse=True)
def _chatbot_encryption_key(monkeypatch):
    from app.services import meta_messaging as mm_module

    monkeypatch.setattr(mm_module.settings, "chatbot_encryption_key", Fernet.generate_key().decode())


def _db_for(channel, site_id="kasa"):
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel
    site_result = MagicMock()
    site_result.scalar_one_or_none.return_value = site_id
    count_result = MagicMock()
    count_result.scalar.return_value = 42

    db = AsyncMock()
    db.execute.side_effect = [channel_result, site_result, count_result]
    return db


@pytest.mark.asyncio
async def test_patch_token_is_re_encrypted_and_decryptable(monkeypatch):
    from app.api import chatbot_admin as ca_module

    audit_calls = []

    async def fake_audit(db, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(ca_module, "log_admin_action", fake_audit)

    channel = _make_channel()
    db = _db_for(channel)

    new_token = "EAANewSystemUserToken123"
    resp = await ca_module.patch_channel(
        channel_id=str(channel.id),
        request_body=ca_module.PatchChannelRequest(page_access_token=new_token),
        request=_fake_request(),
        db=db,
    )

    # Stored value is encrypted, never the raw token.
    assert channel.page_access_token != new_token
    assert decrypt_token(channel.page_access_token) == new_token

    # Response never echoes the token.
    assert "page_access_token" not in resp
    assert resp["id"] == str(channel.id)
    assert resp["total_messages"] == 42

    db.commit.assert_awaited_once()
    assert audit_calls[0]["payload"]["fields_changed"] == ["page_access_token"]
    assert new_token not in str(audit_calls[0]["payload"])


@pytest.mark.asyncio
async def test_patch_config_is_merged_not_replaced(monkeypatch):
    from app.api import chatbot_admin as ca_module

    monkeypatch.setattr(ca_module, "log_admin_action", AsyncMock())

    channel = _make_channel(config={"abbreviations": {"pp": "price please"}, "facebook_page_id": "old_page"})
    db = _db_for(channel)

    resp = await ca_module.patch_channel(
        channel_id=str(channel.id),
        request_body=ca_module.PatchChannelRequest(config={"facebook_page_id": "new_page"}),
        request=_fake_request(),
        db=db,
    )

    assert channel.config == {
        "abbreviations": {"pp": "price please"},
        "facebook_page_id": "new_page",
    }
    assert resp["id"] == str(channel.id)


@pytest.mark.asyncio
async def test_patch_config_merges_when_existing_config_is_a_json_string(monkeypatch):
    """Some readers (chatbot_webhooks, chatbot_query) guard for channel.config
    coming back as a JSON string rather than a dict; patch_channel must merge
    into it instead of 500ing on **existing_config."""
    from app.api import chatbot_admin as ca_module

    monkeypatch.setattr(ca_module, "log_admin_action", AsyncMock())

    channel = _make_channel(config='{"abbreviations": {"pp": "price please"}}')
    db = _db_for(channel)

    resp = await ca_module.patch_channel(
        channel_id=str(channel.id),
        request_body=ca_module.PatchChannelRequest(config={"facebook_page_id": "new_page"}),
        request=_fake_request(),
        db=db,
    )

    assert channel.config == {
        "abbreviations": {"pp": "price please"},
        "facebook_page_id": "new_page",
    }
    assert resp["id"] == str(channel.id)


@pytest.mark.asyncio
async def test_patch_is_active_and_channel_name(monkeypatch):
    from app.api import chatbot_admin as ca_module

    monkeypatch.setattr(ca_module, "log_admin_action", AsyncMock())

    channel = _make_channel(is_active=False, channel_name="@old_name")
    db = _db_for(channel)

    resp = await ca_module.patch_channel(
        channel_id=str(channel.id),
        request_body=ca_module.PatchChannelRequest(is_active=True, channel_name="@new_name"),
        request=_fake_request(),
        db=db,
    )

    assert channel.is_active is True
    assert channel.channel_name == "@new_name"
    assert resp["is_active"] is True
    assert resp["channel_name"] == "@new_name"


@pytest.mark.asyncio
async def test_patch_unknown_channel_404(monkeypatch):
    from app.api import chatbot_admin as ca_module

    monkeypatch.setattr(ca_module, "log_admin_action", AsyncMock())

    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = channel_result

    with pytest.raises(HTTPException) as exc_info:
        await ca_module.patch_channel(
            channel_id=str(uuid.uuid4()),
            request_body=ca_module.PatchChannelRequest(is_active=True),
            request=_fake_request(),
            db=db,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_patch_no_fields_is_422(monkeypatch):
    from app.api import chatbot_admin as ca_module

    monkeypatch.setattr(ca_module, "log_admin_action", AsyncMock())

    channel = _make_channel()
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel
    db = AsyncMock()
    db.execute.return_value = channel_result

    with pytest.raises(HTTPException) as exc_info:
        await ca_module.patch_channel(
            channel_id=str(channel.id),
            request_body=ca_module.PatchChannelRequest(),
            request=_fake_request(),
            db=db,
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_patch_kasa_channel_untouched_by_unrelated_patch(monkeypatch):
    """A PATCH that only flips is_active must not alter the stored token or
    existing config — i.e. kasa's history/config survives an unrelated edit."""
    from app.api import chatbot_admin as ca_module

    monkeypatch.setattr(ca_module, "log_admin_action", AsyncMock())

    original_token = encrypt_token("kasa-original-token")
    channel = _make_channel(
        page_access_token=original_token,
        config={"abbreviations": {"pp": "price please"}},
    )
    db = _db_for(channel)

    await ca_module.patch_channel(
        channel_id=str(channel.id),
        request_body=ca_module.PatchChannelRequest(is_active=False),
        request=_fake_request(),
        db=db,
    )

    assert channel.page_access_token == original_token
    assert channel.config == {"abbreviations": {"pp": "price please"}}
    assert channel.is_active is False


@pytest.mark.asyncio
async def test_connect_channel_accepts_config_and_is_active(monkeypatch):
    """POST /channels: config (incl. facebook_page_id) and is_active no
    longer require a follow-up PATCH/DB write to set."""
    from app.api import chatbot_admin as ca_module

    customer = MagicMock()
    customer.id = uuid.uuid4()

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.side_effect = [customer_result, dup_result]

    created_channel_holder = {}

    def _capture_add(obj):
        created_channel_holder["channel"] = obj

    db.add = MagicMock(side_effect=_capture_add)

    async def _fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = __import__("datetime").datetime(2026, 1, 1)

    db.refresh = AsyncMock(side_effect=_fake_refresh)

    resp = await ca_module.connect_channel(
        request=ca_module.ConnectChannelRequest(
            site_id="sbal",
            platform="instagram",
            platform_page_id="17841499999999",
            page_access_token="EAANewToken",
            config={"facebook_page_id": "17841499999999"},
            is_active=False,
        ),
        db=db,
    )

    channel = created_channel_holder["channel"]
    assert channel.config == {"facebook_page_id": "17841499999999"}
    assert channel.is_active is False
    assert resp["is_active"] is False


def test_patch_with_wrong_admin_key_is_401(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import chatbot_admin as ca_module
    from app.database import get_db

    monkeypatch.setattr(ca_module.settings, "api_secret_key", "test-secret-key")

    app = FastAPI()
    app.include_router(ca_module.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: iter([AsyncMock()])

    client = TestClient(app)
    resp = client.patch(
        f"/api/v1/admin/chatbot/channels/{uuid.uuid4()}",
        json={"is_active": True},
        headers={"X-Admin-Key": "wrong-key"},
    )
    assert resp.status_code == 401
