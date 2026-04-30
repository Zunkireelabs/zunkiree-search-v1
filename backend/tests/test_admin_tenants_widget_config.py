"""Widget config endpoints (Z6).

- GET returns deserialised quick_actions / lead_intents (stored as JSON Text).
- PATCH only updates fields that are explicitly set in the body
  (model_dump(exclude_unset=True)) — fields left out stay untouched.
- JSON-shaped fields (quick_actions, lead_intents) are accepted as native
  lists and re-serialised to JSON strings before write.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.admin_tenants import (
    UpdateTenantRequest,
    _serialise_patch_field,
    _widget_config_to_response,
    get_widget_config,
    patch_widget_config,
)


def _config_mock(quick_actions=None, lead_intents=None):
    config = MagicMock()
    config.brand_name = "Kasa"
    config.tone = "neutral"
    config.primary_color = "#2563eb"
    config.placeholder_text = "Ask a question..."
    config.welcome_message = None
    config.quick_actions = quick_actions
    config.lead_intents = lead_intents
    config.confidence_threshold = 0.25
    config.contact_email = None
    config.contact_phone = None
    return config


def test_serialise_patch_field_encodes_json_columns():
    """quick_actions / lead_intents stored as Text — patch body sends native
    list, helper encodes."""
    assert _serialise_patch_field("quick_actions", ["a", "b"]) == json.dumps(["a", "b"])
    assert _serialise_patch_field("lead_intents", [{"k": "v"}]) == json.dumps([{"k": "v"}])


def test_serialise_patch_field_passes_through_strings_unchanged():
    """If caller already gave a string, don't re-encode."""
    assert _serialise_patch_field("quick_actions", '["a"]') == '["a"]'


def test_serialise_patch_field_passes_through_simple_fields():
    assert _serialise_patch_field("tone", "friendly") == "friendly"
    assert _serialise_patch_field("primary_color", "#ff0000") == "#ff0000"
    assert _serialise_patch_field("confidence_threshold", 0.5) == 0.5


def test_serialise_patch_field_nones_passthrough():
    """None means unset; helper preserves it so caller can clear."""
    assert _serialise_patch_field("welcome_message", None) is None


def test_widget_config_to_response_decodes_json_text():
    config = _config_mock(quick_actions='["help", "shipping"]', lead_intents='[{"intent": "demo"}]')
    resp = _widget_config_to_response(config)
    assert resp.quick_actions == ["help", "shipping"]
    assert resp.lead_intents == [{"intent": "demo"}]


def test_widget_config_to_response_handles_invalid_json():
    """If the stored value isn't valid JSON, keep the raw string rather than
    500 — defensive against hand-edited rows."""
    config = _config_mock(quick_actions="not[json")
    resp = _widget_config_to_response(config)
    assert resp.quick_actions == "not[json"


def test_widget_config_to_response_handles_null():
    config = _config_mock(quick_actions=None)
    resp = _widget_config_to_response(config)
    assert resp.quick_actions is None


@pytest.mark.asyncio
async def test_get_widget_config_returns_decoded_response():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    config = _config_mock(quick_actions='["a","b"]')
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config

    db = AsyncMock()
    db.execute.return_value = config_result

    resp = await get_widget_config(site_id="kasa", customer=customer, db=db)
    assert resp.brand_name == "Kasa"
    assert resp.quick_actions == ["a", "b"]


@pytest.mark.asyncio
async def test_patch_widget_config_only_passes_explicit_fields(monkeypatch):
    """exclude_unset semantics: a body with just `tone` must not also clear
    welcome_message / confidence_threshold."""
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    seen_fields: dict = {}

    async def _update(self, db, customer_id, fields):
        seen_fields.update(fields)
        return _config_mock()

    monkeypatch.setattr(
        "app.api.admin_tenants.TenantProvisioningService.update_widget_config",
        _update,
    )

    body = UpdateTenantRequest(tone="friendly")
    db = AsyncMock()
    await patch_widget_config(site_id="kasa", body=body, customer=customer, db=db)
    assert set(seen_fields.keys()) == {"tone"}
    assert seen_fields["tone"] == "friendly"


@pytest.mark.asyncio
async def test_patch_widget_config_serialises_json_fields(monkeypatch):
    """quick_actions sent as a list lands as JSON-encoded string in the
    fields dict the service receives."""
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    seen_fields: dict = {}

    async def _update(self, db, customer_id, fields):
        seen_fields.update(fields)
        return _config_mock(quick_actions='["help","pricing"]')

    monkeypatch.setattr(
        "app.api.admin_tenants.TenantProvisioningService.update_widget_config",
        _update,
    )

    body = UpdateTenantRequest(quick_actions=["help", "pricing"])
    db = AsyncMock()
    await patch_widget_config(site_id="kasa", body=body, customer=customer, db=db)
    assert seen_fields["quick_actions"] == json.dumps(["help", "pricing"])
