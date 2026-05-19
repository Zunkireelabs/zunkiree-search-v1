"""
Tests for SenderProfileService — cache hit, fetch success, fetch failure paths.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_channel(channel_id=None):
    ch = MagicMock()
    ch.id = channel_id or uuid.uuid4()
    ch.page_access_token = "encrypted-token"
    return ch


def _make_profile(name=None):
    p = MagicMock()
    p.name = name
    p.profile_pic_url = None
    p.fetched_at = None
    p.fetch_failed_at = None
    p.fetch_error = None
    return p


def _make_db(profile=None):
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = profile
    db.execute = AsyncMock(return_value=execute_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_cache_hit_returns_profile_without_meta_call():
    """If a cached profile with a name exists, return it without calling Meta."""
    from app.services.sender_profile_service import SenderProfileService

    channel = _make_channel()
    cached = _make_profile(name="Sadin Shrestha")
    db = _make_db(cached)

    svc = SenderProfileService()
    with patch("app.services.sender_profile_service.get_instagram_profile") as mock_meta:
        result = await svc.get_or_fetch(db, channel, "sender-1")

    assert result is cached
    mock_meta.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_fetch_success_creates_row():
    """On cache miss, fetch from Meta and persist the name."""
    from app.services.sender_profile_service import SenderProfileService

    channel = _make_channel()
    db = _make_db(profile=None)

    svc = SenderProfileService()
    with patch("app.services.sender_profile_service.decrypt_token", return_value="raw-token"), \
         patch("app.services.sender_profile_service.get_instagram_profile", new_callable=AsyncMock,
               return_value={"name": "Test User", "profile_pic": "https://example.com/pic.jpg"}):
        result = await svc.get_or_fetch(db, channel, "sender-2")

    assert result is not None
    assert result.name == "Test User"
    assert result.profile_pic_url == "https://example.com/pic.jpg"
    assert result.fetched_at is not None
    assert result.fetch_failed_at is None
    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_cache_miss_fetch_failure_marks_failed_and_returns_none():
    """On cache miss + Meta returning None, persist fetch_failed_at and return None."""
    from app.services.sender_profile_service import SenderProfileService

    channel = _make_channel()
    db = _make_db(profile=None)

    svc = SenderProfileService()
    with patch("app.services.sender_profile_service.decrypt_token", return_value="raw-token"), \
         patch("app.services.sender_profile_service.get_instagram_profile", new_callable=AsyncMock,
               return_value=None):
        result = await svc.get_or_fetch(db, channel, "sender-3")

    assert result is None
    db.add.assert_called_once()
    added_profile = db.add.call_args[0][0]
    assert added_profile.fetch_failed_at is not None
    assert added_profile.name is None
    db.commit.assert_called_once()
