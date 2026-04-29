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
from app.config import get_settings
from app.services import tenant_provisioning
from app.services.tenant_provisioning import build_widget_script


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


# ---------------------------------------------------------------------------
# Z6.3 — build_widget_script reads WIDGET_DATA_API_URL with prod-URL fallback


def test_build_widget_script_uses_configured_data_api_url(monkeypatch):
    """Stage VPS sets WIDGET_DATA_API_URL to staging-api.zunkireelabs.com;
    build_widget_script must embed that value, not the hardcoded prod URL."""
    settings = get_settings()
    monkeypatch.setattr(settings, "widget_script_base_url", "https://zunkiree-search-v1.vercel.app")
    monkeypatch.setattr(settings, "widget_data_api_url", "https://staging-api.zunkireelabs.com")
    # Reset the once-warned guard so this test is order-independent
    monkeypatch.setattr(tenant_provisioning, "_widget_data_api_url_missing_warned", False)

    script = build_widget_script("kasa")

    assert script is not None
    assert 'data-site-id="kasa"' in script
    assert 'data-api-url="https://staging-api.zunkireelabs.com"' in script
    assert 'data-api-url="https://api.zunkireelabs.com"' not in script
    assert "https://zunkiree-search-v1.vercel.app/zunkiree-widget.iife.js" in script


def test_build_widget_script_falls_back_to_prod_url_with_warning_once(monkeypatch, caplog):
    """Empty WIDGET_DATA_API_URL falls back to prod URL and logs a warning
    exactly once across multiple calls (module-level guard)."""
    import logging

    settings = get_settings()
    monkeypatch.setattr(settings, "widget_script_base_url", "https://zunkiree-search-v1.vercel.app")
    monkeypatch.setattr(settings, "widget_data_api_url", "")
    # Reset the once-warned guard — without this, prior tests in the same run
    # may have already tripped it and caplog would be empty
    monkeypatch.setattr(tenant_provisioning, "_widget_data_api_url_missing_warned", False)

    with caplog.at_level(logging.WARNING, logger=tenant_provisioning.logger.name):
        first = build_widget_script("kasa")
        second = build_widget_script("nuad-thai")

    assert first is not None and second is not None
    assert 'data-api-url="https://api.zunkireelabs.com"' in first
    assert 'data-api-url="https://api.zunkireelabs.com"' in second

    warnings = [r for r in caplog.records if "WIDGET_DATA_API_URL not configured" in r.getMessage()]
    assert len(warnings) == 1, f"Expected one warning, got {len(warnings)}: {warnings}"


def test_build_widget_script_returns_none_when_base_url_missing(monkeypatch):
    """Empty WIDGET_SCRIPT_BASE_URL → None (regression: Z6 contract field
    must be null, not a broken <script> tag)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "widget_script_base_url", "")
    monkeypatch.setattr(settings, "widget_data_api_url", "https://staging-api.zunkireelabs.com")

    assert build_widget_script("kasa") is None


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
