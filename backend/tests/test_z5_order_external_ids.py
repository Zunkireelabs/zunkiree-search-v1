"""
Z5 — persistence of Stella's external IDs onto the local orders row after
a successful sync.

After Z3 wired ConnectorResolver into _sync_to_agenticom, the connector
returns a ConnectorOrderReceipt that was previously parsed only for logging.
Z5 closes that gap: the three new columns (external_backend_type,
external_order_id, external_order_number) get an UPDATE in the same flow,
nested in a second try/except so a local-write failure can't propagate
past the upstream sync that already succeeded.

These tests exercise OrderService._sync_to_agenticom directly with a mocked
AsyncSession + a mocked AgenticomConnector. The connector itself is covered
by test_idempotency.py and test_z3_v1_wire.py — Z5 doesn't change its wire.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.services.connectors.agenticom_connector import ConnectorRequestError
from app.services.connectors.base import ConnectorOrderReceipt
from app.services.order import OrderService


def _order_dict(order_id: str = "order-internal-42") -> dict:
    """Minimal order_dict shape produced by OrderService._order_to_dict."""
    return {
        "id": order_id,
        "order_number": "ZK-ABC123-0001",
        "shopper_email": "shopper@example.test",
        "items": [
            {
                "product_id": "p1",
                "name": "Tee",
                "quantity": 1,
                "price": 1499.0,
                "size": "M",
                "color": None,
                "image": "",
            }
        ],
        "subtotal": 1499.0,
        "total": 1499.0,
        "currency": "NPR",
        "payment_method": "cod",
        "payment_intent_id": None,
        "shipping_address": {
            "name": "Test Shopper",
            "phone": "9800",
            "city": "Kathmandu",
            "country": "NP",
            "address1": "Somewhere",
        },
    }


def _settings_configured(monkeypatch):
    """Make settings.agenticom_* truthy so _sync_to_agenticom doesn't early-return."""
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "agenticom_api_url", "https://example.test", raising=False)
    monkeypatch.setattr(s, "agenticom_sync_secret", "legacy-shared", raising=False)


def _make_mock_connector(*, receipt: ConnectorOrderReceipt = None, raises: Exception = None):
    """Mock connector whose create_order returns receipt or raises."""
    conn = MagicMock()
    if raises is not None:
        conn.create_order = AsyncMock(side_effect=raises)
    else:
        conn.create_order = AsyncMock(return_value=receipt)
    return conn


def _patch_resolver(monkeypatch, connector):
    """Patch ConnectorResolver.for_tenant to return the given connector."""
    from app.services.connectors import resolver as resolver_module

    async def _fake_for_tenant(db, customer_id, backend_type="stella"):
        return connector

    monkeypatch.setattr(
        resolver_module.ConnectorResolver, "for_tenant", staticmethod(_fake_for_tenant)
    )


async def test_successful_sync_persists_all_three_external_id_fields(monkeypatch):
    """Happy path — connector returns a receipt with both IDs populated; the
    persistence UPDATE carries all three fields with backend_type='stella'."""
    _settings_configured(monkeypatch)

    receipt = ConnectorOrderReceipt(
        external_id="ord_xyz",
        external_order_number="STELLA-42",
        status="processing",
        payment_status="cod",
        created_at="2026-04-27T10:00:00Z",
    )
    _patch_resolver(monkeypatch, _make_mock_connector(receipt=receipt))

    db = AsyncMock()
    svc = OrderService()
    customer_id = uuid.uuid4()
    order = _order_dict()

    await svc._sync_to_agenticom(db, customer_id, order, site_id="kasa")

    # One UPDATE statement issued, then committed.
    assert db.execute.await_count == 1
    db.commit.assert_awaited_once()

    # Verify the UPDATE's .values() carried the three locked fields.
    update_stmt = db.execute.await_args.args[0]
    values = update_stmt.compile().params
    assert values["external_backend_type"] == "stella"
    assert values["external_order_id"] == "ord_xyz"
    assert values["external_order_number"] == "STELLA-42"


async def test_connector_failure_skips_persistence_and_swallows(monkeypatch, caplog):
    """When the upstream sync fails (ConnectorRequestError), the function
    must return cleanly without issuing the UPDATE — nothing to persist."""
    import logging

    _settings_configured(monkeypatch)
    err = ConnectorRequestError(502, "upstream blew up")
    _patch_resolver(monkeypatch, _make_mock_connector(raises=err))

    db = AsyncMock()
    svc = OrderService()
    customer_id = uuid.uuid4()
    order = _order_dict()

    with caplog.at_level(logging.WARNING):
        await svc._sync_to_agenticom(db, customer_id, order, site_id="kasa")

    # No UPDATE — connector failure short-circuits before persistence.
    assert db.execute.await_count == 0
    db.commit.assert_not_called()
    assert any("Agenticom returned 502" in r.message for r in caplog.records)


async def test_empty_external_id_is_persisted_as_none(monkeypatch):
    """Connector coerces missing fields to "" via `or ""`. Z5 reverses that
    coercion at write time so the columns hold NULL, not literal empty
    strings — keeps queries on the columns unambiguous."""
    _settings_configured(monkeypatch)

    receipt = ConnectorOrderReceipt(
        external_id="",
        external_order_number="STELLA-NO-ID",
        status="processing",
        payment_status="cod",
        created_at="2026-04-27T10:00:00Z",
    )
    _patch_resolver(monkeypatch, _make_mock_connector(receipt=receipt))

    db = AsyncMock()
    svc = OrderService()

    await svc._sync_to_agenticom(db, uuid.uuid4(), _order_dict(), site_id="kasa")

    update_stmt = db.execute.await_args.args[0]
    values = update_stmt.compile().params
    assert values["external_backend_type"] == "stella"
    assert values["external_order_id"] is None
    assert values["external_order_number"] == "STELLA-NO-ID"


async def test_idempotent_retry_writes_same_values_no_error(monkeypatch):
    """Two syncs of the same logical order: per Z3 + Stella S6, the second
    call gets the cached receipt back. Z5 persists the same values both
    times — no error from the second write since values match."""
    _settings_configured(monkeypatch)

    receipt = ConnectorOrderReceipt(
        external_id="ord_stable",
        external_order_number="STELLA-99",
        status="processing",
        payment_status="cod",
        created_at="2026-04-27T10:00:00Z",
    )
    _patch_resolver(monkeypatch, _make_mock_connector(receipt=receipt))

    db = AsyncMock()
    svc = OrderService()
    customer_id = uuid.uuid4()
    order = _order_dict("order-retry-77")

    await svc._sync_to_agenticom(db, customer_id, order, site_id="kasa")
    await svc._sync_to_agenticom(db, customer_id, order, site_id="kasa")

    # Two UPDATEs + two commits, both carrying the same values.
    assert db.execute.await_count == 2
    assert db.commit.await_count == 2
    for call in db.execute.await_args_list:
        values = call.args[0].compile().params
        assert values["external_order_id"] == "ord_stable"
        assert values["external_order_number"] == "STELLA-99"


async def test_persistence_write_failure_is_swallowed(monkeypatch, caplog):
    """The locked refinement: the upstream sync already succeeded, so a
    failure inside the persistence UPDATE/commit must NOT propagate. The
    customer's checkout is done; the order is already persisted by
    create_order_from_cart. Log a distinct warning so future-you can tell
    'sync failed' apart from 'sync OK, persistence failed'."""
    import logging

    _settings_configured(monkeypatch)

    receipt = ConnectorOrderReceipt(
        external_id="ord_xyz",
        external_order_number="STELLA-101",
        status="processing",
        payment_status="cod",
        created_at="2026-04-27T10:00:00Z",
    )
    _patch_resolver(monkeypatch, _make_mock_connector(receipt=receipt))

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("DB error"))
    svc = OrderService()

    with caplog.at_level(logging.WARNING):
        # Must not raise.
        await svc._sync_to_agenticom(db, uuid.uuid4(), _order_dict(), site_id="kasa")

    # Distinct warning signal proves the nested-except contract.
    assert any(
        "sync succeeded but persisting external IDs failed" in r.message
        for r in caplog.records
    )
    # commit was never reached because execute raised.
    db.commit.assert_not_called()
