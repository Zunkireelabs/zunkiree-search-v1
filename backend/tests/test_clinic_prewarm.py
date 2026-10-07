"""P4 B2: the prewarm loop warms every active clinic-website_type tenant
and tolerates a per-tenant failure without stopping the others."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.customer import Customer
from app.services import clinic_prewarm


def _clinic_customer(site_id):
    return Customer(
        id=uuid.uuid4(), name=site_id, site_id=site_id, api_key="k",
        website_type="clinic", is_active=True,
    )


@pytest.mark.asyncio
async def test_prewarm_resolves_org_for_every_active_clinic_tenant():
    customers = [_clinic_customer("dental-city"), _clinic_customer("client-2")]

    with patch.object(clinic_prewarm, "_clinic_customers", AsyncMock(return_value=customers)), \
         patch.object(clinic_prewarm, "async_session_maker") as session_maker, \
         patch.object(clinic_prewarm, "_resolve_org", AsyncMock()) as resolve_org:
        session_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        warmed = await clinic_prewarm._prewarm_org_cache_once()

    assert warmed == 2
    assert resolve_org.await_count == 2


@pytest.mark.asyncio
async def test_prewarm_one_tenant_failure_does_not_block_the_others():
    customers = [_clinic_customer("dental-city"), _clinic_customer("client-2")]

    async def _resolve_org(db, customer):
        if customer.site_id == "dental-city":
            raise RuntimeError("ClinicMD down")

    with patch.object(clinic_prewarm, "_clinic_customers", AsyncMock(return_value=customers)), \
         patch.object(clinic_prewarm, "async_session_maker") as session_maker, \
         patch.object(clinic_prewarm, "_resolve_org", _resolve_org):
        session_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        warmed = await clinic_prewarm._prewarm_org_cache_once()

    assert warmed == 1  # client-2 only; dental-city's failure was swallowed


@pytest.mark.asyncio
async def test_not_configured_backend_logs_one_warning_without_traceback(caplog):
    """SBAL-Z3 log noise: the prod API has no backend env at all (the brain
    lives on the clinic lane) — ZennlyNotConfigured/ClinicMdNotConfigured
    must log one clean WARNING line, never a full traceback, on every
    rewarm."""
    import logging

    from app.services.zennly_client import ZennlyNotConfigured

    customers = [_clinic_customer("sbal")]

    async def _resolve_org(db, customer):
        raise ZennlyNotConfigured()

    with patch.object(clinic_prewarm, "_clinic_customers", AsyncMock(return_value=customers)), \
         patch.object(clinic_prewarm, "async_session_maker") as session_maker, \
         patch.object(clinic_prewarm, "_resolve_org", _resolve_org):
        session_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        with caplog.at_level(logging.WARNING, logger="zunkiree.clinic_prewarm"):
            warmed = await clinic_prewarm._prewarm_org_cache_once()

    assert warmed == 0
    records = [r for r in caplog.records if "sbal" in r.getMessage()]
    assert len(records) == 1
    assert "backend_not_configured" in records[0].getMessage()
    assert records[0].exc_info is None  # no traceback attached
