"""
P3-WIDGET-THROUGH-ORCA-BRIEF Part B (B1): widget_configs.chat_stream_url is
nullable, https:// validated, admin-editable, clearable (rollback = clear
the field, config only — brief §2), and returned by the widget config
endpoint.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.api.admin import UpdateConfigRequest, update_config
from app.api.widget import get_widget_config
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig


def _customer() -> Customer:
    return Customer(
        id=uuid.uuid4(), name="Dental Co", site_id="dental-city",
        api_key="key", website_type="clinic", is_active=True,
    )


# ---------- validation ----------


def test_chat_stream_url_rejects_non_https():
    with pytest.raises(ValidationError):
        UpdateConfigRequest(chat_stream_url="http://gateway.example.com/v1/widget/stream")


def test_chat_stream_url_accepts_https():
    req = UpdateConfigRequest(chat_stream_url="https://gateway.example.com/v1/widget/stream")
    assert req.chat_stream_url == "https://gateway.example.com/v1/widget/stream"


def test_chat_stream_url_omitted_is_fine():
    req = UpdateConfigRequest(brand_name="X")
    assert "chat_stream_url" not in req.model_dump(exclude_unset=True)


# ---------- admin PUT /admin/config/{customer_id}: set + clear ----------


async def _run_update(db, customer, existing_config, request: UpdateConfigRequest):
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = existing_config
    db.execute = AsyncMock(side_effect=[customer_result, config_result])
    db.commit = AsyncMock()
    db.add = MagicMock()
    return await update_config(customer.site_id, request, db=db, _="admin-key")


@pytest.mark.asyncio
async def test_update_config_sets_chat_stream_url():
    customer = _customer()
    config = WidgetConfig(customer_id=customer.id, brand_name="Dental Co")
    db = AsyncMock()

    await _run_update(db, customer, config, UpdateConfigRequest(
        chat_stream_url="https://gateway.example.com/v1/widget/stream",
    ))

    assert config.chat_stream_url == "https://gateway.example.com/v1/widget/stream"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_config_clears_chat_stream_url_on_explicit_null():
    """Rollback (brief §2): clearing the field, config only, no deploy."""
    customer = _customer()
    config = WidgetConfig(customer_id=customer.id, brand_name="Dental Co")
    config.chat_stream_url = "https://gateway.example.com/v1/widget/stream"
    db = AsyncMock()

    await _run_update(db, customer, config, UpdateConfigRequest(chat_stream_url=None))

    assert config.chat_stream_url is None


@pytest.mark.asyncio
async def test_update_config_omitting_field_leaves_it_untouched():
    customer = _customer()
    config = WidgetConfig(customer_id=customer.id, brand_name="Dental Co")
    config.chat_stream_url = "https://gateway.example.com/v1/widget/stream"
    db = AsyncMock()

    await _run_update(db, customer, config, UpdateConfigRequest(brand_name="New Name"))

    assert config.chat_stream_url == "https://gateway.example.com/v1/widget/stream"
    assert config.brand_name == "New Name"


# ---------- GET /widget/config/{site_id} surfaces it ----------


def _widget_config(customer_id) -> WidgetConfig:
    # Column-level defaults are applied on INSERT, not on plain
    # instantiation — set them explicitly for a config that's never flushed.
    return WidgetConfig(
        customer_id=customer_id, brand_name="Dental Co", tone="neutral",
        primary_color="#2563eb", placeholder_text="Ask a question...",
        show_sources=True, show_suggestions=True, enable_shopping=False,
    )


@pytest.mark.asyncio
async def test_widget_config_endpoint_returns_chat_stream_url_when_set():
    customer = _customer()
    config = _widget_config(customer.id)
    config.chat_stream_url = "https://gateway.example.com/v1/widget/stream"

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[customer_result, config_result])

    response = await get_widget_config("dental-city", db=db)

    assert response.chat_stream_url == "https://gateway.example.com/v1/widget/stream"


@pytest.mark.asyncio
async def test_widget_config_endpoint_defaults_to_none_when_unset():
    customer = _customer()
    config = _widget_config(customer.id)

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[customer_result, config_result])

    response = await get_widget_config("dental-city", db=db)

    assert response.chat_stream_url is None
