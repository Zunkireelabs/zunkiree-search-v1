"""SBAL-Z2 item 5: POST /admin/chatbot/channels/{id}/ice-breakers — values
come from channel.config, never hardcoded, so this is one endpoint/script
for every clinic tenant's channel."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _make_channel(config=None):
    ch = MagicMock()
    ch.id = uuid.uuid4()
    ch.platform_page_id = "17841400000000"
    ch.page_access_token = "encrypted-token"
    ch.config = config if config is not None else {}
    return ch


@pytest.mark.asyncio
async def test_sets_ice_breakers_from_channel_config(monkeypatch):
    from app.api import chatbot_admin as ca_module

    channel = _make_channel(config={
        "ice_breakers": [
            {"question": "Book an appointment", "payload": "Book an appointment"},
            {"question": "Services & prices", "payload": "Services & prices"},
        ],
        "facebook_page_id": "fb-page-1",
    })
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel
    db = AsyncMock()
    db.execute = AsyncMock(return_value=channel_result)

    fake_meta_client = MagicMock()
    fake_meta_client.set_ice_breakers = AsyncMock(return_value={"success": True})

    with patch("app.services.meta_messaging.decrypt_token", return_value="plain-token"), \
         patch("app.services.meta_messaging.get_meta_messaging_client", return_value=fake_meta_client):
        resp = await ca_module.set_ice_breakers(channel_id=str(channel.id), db=db)

    fake_meta_client.set_ice_breakers.assert_awaited_once_with(
        page_id="fb-page-1", access_token="plain-token", questions=channel.config["ice_breakers"],
    )
    assert resp["questions_set"] == 2


@pytest.mark.asyncio
async def test_falls_back_to_platform_page_id_when_no_facebook_page_id_configured(monkeypatch):
    from app.api import chatbot_admin as ca_module

    channel = _make_channel(config={"ice_breakers": [{"question": "Hours", "payload": "Hours"}]})
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel
    db = AsyncMock()
    db.execute = AsyncMock(return_value=channel_result)

    fake_meta_client = MagicMock()
    fake_meta_client.set_ice_breakers = AsyncMock(return_value={"success": True})

    with patch("app.services.meta_messaging.decrypt_token", return_value="plain-token"), \
         patch("app.services.meta_messaging.get_meta_messaging_client", return_value=fake_meta_client):
        await ca_module.set_ice_breakers(channel_id=str(channel.id), db=db)

    assert fake_meta_client.set_ice_breakers.await_args.kwargs["page_id"] == channel.platform_page_id


@pytest.mark.asyncio
async def test_404_on_unknown_channel():
    from app.api import chatbot_admin as ca_module

    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=channel_result)

    with pytest.raises(HTTPException) as exc_info:
        await ca_module.set_ice_breakers(channel_id=str(uuid.uuid4()), db=db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_422_when_config_has_no_ice_breakers():
    from app.api import chatbot_admin as ca_module

    channel = _make_channel(config={})
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel
    db = AsyncMock()
    db.execute = AsyncMock(return_value=channel_result)

    with pytest.raises(HTTPException) as exc_info:
        await ca_module.set_ice_breakers(channel_id=str(channel.id), db=db)
    assert exc_info.value.status_code == 422
