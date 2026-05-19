"""
Tests for the order sync payload construction in OrderService._sync_to_agenticom.
Verifies IG orders use source/external_id identity and web orders keep email path.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _split_name unit tests (pure function, no imports needed at collection time)
# ---------------------------------------------------------------------------

def test_split_name_two_words():
    from app.services.order import _split_name
    assert _split_name("Sadin Shrestha") == ("Sadin", "Shrestha")


def test_split_name_single_word():
    from app.services.order import _split_name
    assert _split_name("madonna") == ("madonna", None)


def test_split_name_empty():
    from app.services.order import _split_name
    assert _split_name("") == (None, None)


def test_split_name_extra_spaces():
    from app.services.order import _split_name
    first, last = _split_name("  Sadin  Shrestha  ")
    assert first == "Sadin"
    assert last == "Shrestha"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_order_dict(**overrides):
    base = {
        "id": str(uuid.uuid4()),
        "order_number": "ZK-ABC-1234",
        "customer_id": str(uuid.uuid4()),
        "session_id": "dm:ch-1:sender-1",
        "shopper_email": None,
        "items": [
            {
                "product_id": "prod-uuid",
                "name": "Silk Shirt",
                "quantity": 1,
                "price": 2500,
                "size": "M",
                "color": None,
                "image": "",
            }
        ],
        "subtotal": 2500,
        "total": 2500,
        "currency": "NPR",
        "status": "processing",
        "payment_status": "cod",
        "payment_intent_id": None,
        "payment_method": "cod",
        "billing_address": None,
        "shipping_address": '{"name": "Sadin", "location": "Kathmandu", "phone": "9800000000"}',
        "notes": None,
        "created_at": "2026-05-19T10:00:00",
        "updated_at": "2026-05-19T10:00:00",
    }
    base.update(overrides)
    return base


def _make_settings():
    s = MagicMock()
    s.agenticom_api_url = "https://api-dev-app.stella-commerce.com"
    s.agenticom_sync_secret = "test-secret"
    return s


async def _call_sync(order_dict):
    from app.services.order import OrderService

    captured = {}

    async def fake_create_order(draft, idempotency_key):
        captured["draft"] = draft
        r = MagicMock()
        r.external_id = "stella-order-1"
        r.external_order_number = "STELLA-001"
        return r

    mock_connector = AsyncMock()
    mock_connector.create_order = fake_create_order

    svc = OrderService()
    with patch("app.services.order.get_settings", return_value=_make_settings()), \
         patch("app.services.order.ConnectorResolver") as mock_resolver_cls, \
         patch("app.services.order.update"):
        mock_resolver_cls.for_tenant = AsyncMock(return_value=mock_connector)
        await svc._sync_to_agenticom(
            db=AsyncMock(),
            customer_id=uuid.uuid4(),
            order_dict=order_dict,
            site_id="kasa-clothing",
        )
    return captured.get("draft")


@pytest.mark.asyncio
async def test_ig_order_uses_instagram_source_and_external_id():
    """IG order → source='instagram', external_id='ig_<sender_id>', email=None."""
    order_dict = _make_order_dict(
        platform_channel="instagram",
        platform_sender_id="12345",
        customer_name="Sadin Shrestha",
    )
    draft = await _call_sync(order_dict)

    assert draft is not None
    assert draft.source == "instagram"
    assert draft.external_id == "ig_12345"
    assert draft.email is None
    assert draft.first_name == "Sadin"
    assert draft.last_name == "Shrestha"


@pytest.mark.asyncio
async def test_ig_order_checkout_name_split_correctly():
    """IG order with checkout name → first/last split correctly."""
    order_dict = _make_order_dict(
        platform_channel="instagram",
        platform_sender_id="99999",
        customer_name="Sadin Shrestha",
    )
    draft = await _call_sync(order_dict)

    assert draft.first_name == "Sadin"
    assert draft.last_name == "Shrestha"
    assert draft.external_id == "ig_99999"


@pytest.mark.asyncio
async def test_ig_order_no_name_sends_null_names():
    """IG order with no customer_name → first_name=None, last_name=None (Stella accepts nulls)."""
    order_dict = _make_order_dict(
        platform_channel="instagram",
        platform_sender_id="77777",
    )
    draft = await _call_sync(order_dict)

    assert draft.source == "instagram"
    assert draft.external_id == "ig_77777"
    assert draft.first_name is None
    assert draft.last_name is None
    assert draft.email is None


@pytest.mark.asyncio
async def test_web_order_uses_email_path():
    """Web order → source='web', email from shopper_email, no external_id."""
    order_dict = _make_order_dict(shopper_email="customer@example.com")
    draft = await _call_sync(order_dict)

    assert draft.source == "web"
    assert draft.email == "customer@example.com"
    assert draft.external_id is None


@pytest.mark.asyncio
async def test_web_order_fallback_email_when_no_shopper_email():
    """Web order with no shopper_email → falls back to site_id@orders.zunkireelabs.com."""
    order_dict = _make_order_dict(shopper_email=None)
    draft = await _call_sync(order_dict)

    assert draft.email == "kasa-clothing@orders.zunkireelabs.com"
    assert draft.source == "web"
