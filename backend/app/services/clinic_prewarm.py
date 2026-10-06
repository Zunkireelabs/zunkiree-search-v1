"""P4 B2: erase the cold-start tax on the clinic agent lane.

Measured on stage (P4-VOICE-FEEL-BRIEF §2, B3 instrumentation): a cold
first LLM call ran 2629ms vs ~1150ms warm, and a cold `_resolve_org` (DB
credential read + ClinicMD `get_org`/`list_branches`) cost 1370ms. Both
land on whichever visitor's turn happens to be first after a deploy or an
idle period — this background loop pays that cost once, off the request
path, instead.

Two independent warm-ups, run once at container start and then the org
cache re-warmed on a schedule shorter than its own TTL so it never expires
cold again:
  (a) `_resolve_org` for every clinic-website_type tenant (fills
      `_ORG_CACHE` in clinic_tools.py).
  (b) one cheap OpenAI chat completion, to open the TLS connection the
      real first turn would otherwise pay for.

No behaviour change to the call path itself — `_resolve_org` already
no-ops on a warm cache, and this only ever runs the SAME code turns
already run. Uses its own short-lived DB session per cycle (never held
across the ClinicMD HTTP call — see `_resolve_org_uncached`'s own note)
to respect the lane's 2-socket budget (DB_POOL_SIZE=2, DB_MAX_OVERFLOW=0).
"""
import asyncio
import logging
import time

from sqlalchemy import select

from app.database import async_session_maker
from app.models.customer import Customer
from app.services.clinic_tools import _resolve_org  # noqa: SLF001 (intentional reuse — see module docstring)
from app.services.clinicmd_client import ClinicMdNotConfigured
from app.services.openai_client import get_openai_client
from app.services.zennly_client import ZennlyNotConfigured

logger = logging.getLogger("zunkiree.clinic_prewarm")

# Half the org cache's own 600s TTL (clinic_tools._ORG_CACHE_TTL_SECONDS):
# re-warming at 300s means a cache entry is never older than 300s when a
# real visitor turn hits it, well inside the 600s staleness bound that
# TTL was chosen for.
_REWARM_INTERVAL_SECONDS = 300


async def _clinic_customers(db) -> list[Customer]:
    result = await db.execute(
        select(Customer).where(Customer.website_type == "clinic", Customer.is_active == True)  # noqa: E712
    )
    return list(result.scalars().all())


async def _prewarm_org_cache_once() -> int:
    """Resolve org/branches for every active clinic tenant. Returns the
    count warmed. Errors are logged and swallowed per-tenant — one tenant's
    ClinicMD outage must not stop the others from warming or crash the loop."""
    warmed = 0
    async with async_session_maker() as db:
        customers = await _clinic_customers(db)
        for customer in customers:
            try:
                await _resolve_org(db, customer)
                warmed += 1
            except (ZennlyNotConfigured, ClinicMdNotConfigured):
                # SBAL-Z3 log noise: expected on the prod API, which has no
                # backend env at all (the brain lives on the clinic lane) —
                # one line, never a traceback, every rewarm.
                logger.warning(
                    "[CLINIC-PREWARM] backend_not_configured site_id=%s — skipping (expected off the clinic lane)",
                    customer.site_id,
                )
            except Exception:
                logger.warning(
                    "[CLINIC-PREWARM] resolve_org_failed site_id=%s", customer.site_id, exc_info=True
                )
    return warmed


async def _prewarm_openai_once() -> None:
    """One cheap completion to open the chat client's connection before any
    real visitor pays for it. Model/tokens kept minimal — this call's own
    answer is never used."""
    try:
        client = get_openai_client("chat")
        from app.config import get_settings
        await client.chat.completions.create(
            model=get_settings().llm_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
    except Exception:
        logger.warning("[CLINIC-PREWARM] openai_warmup_failed", exc_info=True)


async def run_clinic_prewarm_loop(stop_event: asyncio.Event) -> None:
    """Runs until `stop_event` is set: one immediate warm-up pass (org cache
    + OpenAI), then re-warms the org cache every `_REWARM_INTERVAL_SECONDS`
    so it never crosses its own TTL cold. Started as a fire-and-forget
    asyncio task from the lifespan, same pattern as the inbound dispatcher."""
    t0 = time.monotonic()
    warmed = await _prewarm_org_cache_once()
    await _prewarm_openai_once()
    logger.info(
        "[CLINIC-PREWARM] startup_warmup_done tenants=%d latency_ms=%.0f",
        warmed, (time.monotonic() - t0) * 1000,
    )

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_REWARM_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            break
        t0 = time.monotonic()
        warmed = await _prewarm_org_cache_once()
        logger.info(
            "[CLINIC-PREWARM] rewarm_done tenants=%d latency_ms=%.0f",
            warmed, (time.monotonic() - t0) * 1000,
        )
