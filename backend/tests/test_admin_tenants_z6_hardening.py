"""Z6 stage hardening sweep regressions (Z6.2 + Z6.4).

- Z6.2: get_analytics accepts tz-aware ISO `from` / `to` without raising
  "can't compare offset-naive and offset-aware datetimes". Boundary-normalize
  via astimezone(utc).replace(tzinfo=None) preserves the wall-clock semantic
  against naive UTC `created_at` columns.
- Z6.4: push_stella_credentials and register_webhook return a clean
  503 service_unavailable envelope (NOT bare 500) when the encryption helper
  is unavailable. Future misconfig surfaces as a contract-shaped error.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.admin_tenants import (
    RegisterWebhookRequest,
    StellaCredentialsRequest,
    get_analytics,
    push_stella_credentials,
    register_webhook,
)
from app.config import get_settings


def _analytics_mock_db():
    """Build an AsyncMock db whose four execute() calls return zero-row
    aggregates."""
    agg_row = MagicMock()
    agg_row.total = 0
    agg_row.with_answer = 0
    agg_row.p95 = None
    agg_result = MagicMock()
    agg_result.one.return_value = agg_row

    leads_result = MagicMock()
    leads_result.scalar.return_value = 0

    orders_result = MagicMock()
    orders_result.scalar.return_value = 0

    top_result = MagicMock()
    top_result.all.return_value = []

    db = AsyncMock()
    db.execute.side_effect = [agg_result, leads_result, orders_result, top_result]
    return db


def _captured_where_bounds(db: AsyncMock) -> tuple[datetime, datetime]:
    """Pull (from_, to) out of the first execute() call's compiled statement.
    SQLAlchemy 2.x exposes bound parameters via stmt.compile().params.
    """
    stmt = db.execute.call_args_list[0].args[0]
    params = stmt.compile().params
    # WHERE created_at >= from_  →  bind name created_at_1
    # WHERE created_at <= to     →  bind name created_at_2
    return params["created_at_1"], params["created_at_2"]


@pytest.mark.asyncio
async def test_analytics_accepts_tz_aware_utc():
    """+00:00 input must not raise the naive-vs-aware comparison error."""
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    db = _analytics_mock_db()

    from_ = datetime(2026, 4, 21, 0, 0, 0, tzinfo=timezone.utc)
    to = datetime(2026, 4, 28, 0, 0, 0, tzinfo=timezone.utc)

    resp = await get_analytics(
        site_id="kasa", from_=from_, to=to, customer=customer, db=db
    )

    assert resp.queries_total == 0
    assert resp.queries_with_answer == 0
    assert resp.leads_captured == 0
    assert resp.orders_via_widget == 0
    assert resp.top_questions == []

    # Bound values are naive UTC after normalization
    bound_from, bound_to = _captured_where_bounds(db)
    assert bound_from == datetime(2026, 4, 21, 0, 0, 0)
    assert bound_to == datetime(2026, 4, 28, 0, 0, 0)
    assert bound_from.tzinfo is None and bound_to.tzinfo is None


@pytest.mark.asyncio
async def test_analytics_npt_offset_converts_to_utc_then_strips():
    """+05:45 (NPT) must convert to wall-clock UTC, not be stripped naively.
    2026-04-21T05:00:00+05:45 == 2026-04-20T23:15:00Z. A bare .replace(tzinfo=None)
    would land on 2026-04-21T05:00:00 — 5h45m off."""
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    db = _analytics_mock_db()

    npt = timezone(timedelta(hours=5, minutes=45))
    from_ = datetime(2026, 4, 21, 5, 0, 0, tzinfo=npt)
    to = datetime(2026, 4, 28, 5, 0, 0, tzinfo=npt)

    await get_analytics(
        site_id="kasa", from_=from_, to=to, customer=customer, db=db
    )

    bound_from, bound_to = _captured_where_bounds(db)
    assert bound_from == datetime(2026, 4, 20, 23, 15, 0)
    assert bound_to == datetime(2026, 4, 27, 23, 15, 0)
    # Equivalence: caller passing the naive UTC equivalent gets the same bound.
    db2 = _analytics_mock_db()
    await get_analytics(
        site_id="kasa",
        from_=datetime(2026, 4, 20, 23, 15, 0),
        to=datetime(2026, 4, 27, 23, 15, 0),
        customer=customer,
        db=db2,
    )
    assert _captured_where_bounds(db2) == (bound_from, bound_to)


@pytest.mark.asyncio
async def test_analytics_one_sided_tz_mismatch_does_not_raise():
    """from tz-aware (+05:45), to omitted: independent normalization makes
    from naive UTC; default to is datetime.utcnow() (also naive). Comparison
    works without the offset-naive vs offset-aware crash. (§9.6 sanity)."""
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    db = _analytics_mock_db()

    npt = timezone(timedelta(hours=5, minutes=45))
    from_ = datetime(2026, 4, 21, 0, 0, 0, tzinfo=npt)

    resp = await get_analytics(
        site_id="kasa", from_=from_, to=None, customer=customer, db=db
    )

    assert resp.queries_total == 0
    bound_from, bound_to = _captured_where_bounds(db)
    # from_ converted to naive UTC: 2026-04-20T18:15:00
    assert bound_from == datetime(2026, 4, 20, 18, 15, 0)
    # to defaulted to a naive datetime.utcnow(); just confirm it's naive +
    # later than from
    assert bound_to.tzinfo is None
    assert bound_to > bound_from


@pytest.mark.asyncio
async def test_push_stella_credentials_returns_503_when_encryption_key_missing(
    monkeypatch,
):
    """Future misconfig (e.g., Phase C .env render bug) must surface as
    503 service_unavailable with a JSON envelope, not bare 500."""
    # Per §9.2: monkeypatch the lru-cached Settings instance so encrypt()
    # rebuilds Fernet from the empty key and raises.
    monkeypatch.setattr(get_settings(), "backend_credentials_encryption_key", "")

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    creds_lookup = MagicMock()
    creds_lookup.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = creds_lookup

    body = StellaCredentialsRequest(
        sync_key_id="ssk_live_X",
        sync_key_secret="ssk_sec_X_padded_to_realistic_length_xxx",
    )

    with pytest.raises(HTTPException) as exc:
        await push_stella_credentials(
            site_id="kasa", body=body, customer=customer, db=db
        )

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "service_unavailable"
    assert "temporarily unavailable" in exc.value.detail["message"].lower()
    # No row added — encryption failure must short-circuit before db writes
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_webhook_returns_503_when_encryption_key_missing(monkeypatch):
    """Same defensive envelope on the outbound webhook registration path."""
    monkeypatch.setattr(get_settings(), "backend_credentials_encryption_key", "")

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    db = AsyncMock()

    body = RegisterWebhookRequest(
        url="https://stella.example/inbound/zunkiree",
        events=["lead.captured"],
    )

    with pytest.raises(HTTPException) as exc:
        await register_webhook(
            site_id="kasa", body=body, customer=customer, db=db
        )

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "service_unavailable"
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
