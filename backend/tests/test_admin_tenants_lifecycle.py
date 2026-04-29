"""POST/GET/PATCH/DELETE /admin/tenants handler tests (Z6).

Service-level: TenantProvisioningService.provision is exercised against a real
in-memory style mock so the customer/widget_config writes can be observed.
Route-level: handlers are called with mocked DB sessions to verify response
shape and status codes.
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.admin_tenants import (
    CreateTenantRequest,
    UpdateTenantRequest,
    create_tenant,
    delete_tenant,
    get_tenant,
    patch_tenant,
)
from app.services.tenant_provisioning import (
    TenantAlreadyExistsError,
    TenantProvisioningService,
    generate_admin_token,
    generate_webhook_signing_secret,
)


# ---------- Token + secret format ----------


def test_generate_admin_token_format():
    token_id, secret = generate_admin_token()
    assert token_id.startswith("zka_live_")
    assert secret.startswith("zka_sec_")
    assert len(secret) >= 16
    # token_id and secret are independent; never equal
    assert token_id != secret


def test_generate_webhook_signing_secret_format():
    s = generate_webhook_signing_secret()
    assert s.startswith("whsec_")
    assert len(s) > 32


# ---------- provision: duplicate site_id raises ----------


@pytest.mark.asyncio
async def test_provision_duplicate_site_id_raises_typed_error():
    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.site_id = "kasa"
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = existing

    db = AsyncMock()
    db.execute.return_value = customer_result

    service = TenantProvisioningService()
    with pytest.raises(TenantAlreadyExistsError) as exc:
        await service.provision(
            db,
            site_id="kasa",
            brand_name="Kasa",
            contact_email="ops@kasa.example",
            website_type="ecommerce",
            stella_merchant_id="mrch_kasa",
        )
    assert exc.value.site_id == "kasa"


# ---------- create_tenant route returns 409 on duplicate ----------


@pytest.mark.asyncio
async def test_create_tenant_route_returns_409_on_duplicate(monkeypatch):
    body = CreateTenantRequest(
        stella_merchant_id="mrch_kasa",
        site_id="kasa",
        brand_name="Kasa",
        contact_email="ops@kasa.example",
        website_type="ecommerce",
    )

    async def _raise(*args, **kwargs):
        raise TenantAlreadyExistsError("kasa")

    monkeypatch.setattr(
        "app.api.admin_tenants.TenantProvisioningService.provision", _raise
    )
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await create_tenant(body=body, db=db)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "tenant_already_exists"


# ---------- create_tenant route returns full secrets only on first creation ----------


@pytest.mark.asyncio
async def test_create_tenant_route_returns_secrets_in_response(monkeypatch):
    body = CreateTenantRequest(
        stella_merchant_id="mrch_kasa",
        site_id="kasa",
        brand_name="Kasa",
        contact_email="ops@kasa.example",
        website_type="ecommerce",
    )

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"
    customer.stella_merchant_id = "mrch_kasa"

    widget_config = MagicMock()
    widget_config.brand_name = "Kasa"
    widget_config.tone = "neutral"
    widget_config.primary_color = "#2563eb"
    widget_config.placeholder_text = "Ask a question..."
    widget_config.welcome_message = None
    widget_config.quick_actions = None
    widget_config.lead_intents = None
    widget_config.confidence_threshold = 0.25
    widget_config.contact_email = "ops@kasa.example"
    widget_config.contact_phone = None

    from app.services.tenant_provisioning import ProvisionResult

    fake_result = ProvisionResult(
        customer=customer,
        widget_config=widget_config,
        admin_token_id="zka_live_abc",
        admin_token_secret="zka_sec_xyz_padded_to_realistic_length_xxxxxxxxxx",
        webhook_signing_secret="whsec_xyz_padded_to_realistic_length",
        widget_script='<script src="https://x.example/zunkiree-widget.iife.js" data-site-id="kasa" data-api-url="https://api.zunkireelabs.com"></script>',
    )

    async def _ok(self, *args, **kwargs):
        return fake_result

    monkeypatch.setattr(
        "app.api.admin_tenants.TenantProvisioningService.provision", _ok
    )

    db = AsyncMock()
    resp = await create_tenant(body=body, db=db)
    assert resp.site_id == "kasa"
    assert resp.admin_token == "zka_sec_xyz_padded_to_realistic_length_xxxxxxxxxx"
    assert resp.admin_token_id == "zka_live_abc"
    assert resp.webhook_signing_secret == "whsec_xyz_padded_to_realistic_length"
    assert resp.widget_script and "kasa" in resp.widget_script
    assert resp.widget_config.brand_name == "Kasa"
    assert resp.widget_config.contact_email == "ops@kasa.example"


# ---------- get_tenant returns metadata, no secrets ----------


@pytest.mark.asyncio
async def test_get_tenant_returns_metadata_only():
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"
    customer.name = "Kasa"
    customer.stella_merchant_id = "mrch_kasa"
    customer.website_type = "ecommerce"
    customer.is_active = True
    customer.created_at = datetime.utcnow()
    customer.updated_at = datetime.utcnow()

    config = MagicMock()
    config.brand_name = "Kasa"
    config.tone = "neutral"
    config.primary_color = "#2563eb"
    config.placeholder_text = "Ask a question..."
    config.welcome_message = None
    config.quick_actions = None
    config.lead_intents = None
    config.confidence_threshold = 0.25
    config.contact_email = "ops@kasa.example"
    config.contact_phone = None

    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config

    db = AsyncMock()
    db.execute.return_value = config_result

    resp = await get_tenant(site_id="kasa", customer=customer, db=db)
    assert resp.site_id == "kasa"
    assert resp.stella_merchant_id == "mrch_kasa"
    assert resp.widget_config.brand_name == "Kasa"
    serialized = resp.model_dump()
    # No secret leakage
    assert "admin_token" not in serialized
    assert "webhook_signing_secret" not in serialized


# ---------- patch_tenant updates only supplied fields ----------


@pytest.mark.asyncio
async def test_patch_tenant_partial_update(monkeypatch):
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"
    customer.name = "Kasa"
    customer.stella_merchant_id = "mrch_kasa"
    customer.website_type = "ecommerce"
    customer.is_active = True
    customer.created_at = datetime.utcnow()
    customer.updated_at = datetime.utcnow()

    config = MagicMock()
    config.brand_name = "Kasa"
    config.tone = "friendly"  # what we just patched
    config.primary_color = "#2563eb"
    config.placeholder_text = "Ask a question..."
    config.welcome_message = "Hi!"  # what we just patched
    config.quick_actions = None
    config.lead_intents = None
    config.confidence_threshold = 0.25
    config.contact_email = None
    config.contact_phone = None

    async def _update(self, db, customer_id, fields):
        # Verify only supplied fields are passed in (welcome_message + tone)
        assert set(fields.keys()) == {"tone", "welcome_message"}
        assert fields["tone"] == "friendly"
        assert fields["welcome_message"] == "Hi!"
        return config

    monkeypatch.setattr(
        "app.api.admin_tenants.TenantProvisioningService.update_widget_config",
        _update,
    )

    body = UpdateTenantRequest(tone="friendly", welcome_message="Hi!")
    db = AsyncMock()
    resp = await patch_tenant(site_id="kasa", body=body, customer=customer, db=db)
    assert resp.widget_config.tone == "friendly"
    assert resp.widget_config.welcome_message == "Hi!"


# ---------- delete_tenant requires confirm=true ----------


def _fake_request():
    """Stand-in Request for direct handler calls. Z-Ops hardening added a
    `request: Request` parameter to delete_tenant for audit-log wiring."""
    from fastapi import Request
    req = MagicMock(spec=Request)
    req.headers = {}
    req.client = MagicMock(host="127.0.0.1")
    state = MagicMock(spec=[])
    req.state = state
    return req


@pytest.mark.asyncio
async def test_delete_tenant_requires_confirm_flag():
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await delete_tenant(site_id="kasa", request=_fake_request(), confirm=False, db=db)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "confirmation_required"


@pytest.mark.asyncio
async def test_delete_tenant_404_when_missing():
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = customer_result

    with pytest.raises(HTTPException) as exc:
        await delete_tenant(site_id="ghost", request=_fake_request(), confirm=True, db=db)
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "tenant_not_found"


@pytest.mark.asyncio
async def test_delete_tenant_runs_raw_cascade_when_present(monkeypatch):
    """Raw SQL DELETE so DB-level CASCADE handles every related table."""
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"
    customer.name = "Kasa"
    customer.stella_merchant_id = None
    customer.is_active = True
    customer.website_type = None
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer

    # Pinecone + audit are wired post-delete (Z-Ops hardening); stub them so
    # this test stays focused on the DB cascade path.
    from app.api import admin_tenants as tenants_module
    fake_vss = MagicMock()
    fake_vss.delete_namespace = AsyncMock()
    monkeypatch.setattr(tenants_module, "get_vector_store_service", lambda: fake_vss)

    async def _noop_audit(db, **kwargs):
        return None
    monkeypatch.setattr(tenants_module, "log_admin_action", _noop_audit)

    db = AsyncMock()
    # First .execute is the SELECT, second is the DELETE
    db.execute.side_effect = [customer_result, MagicMock()]

    await delete_tenant(site_id="kasa", request=_fake_request(), confirm=True, db=db)
    assert db.execute.await_count == 2
    assert db.commit.await_count == 1
