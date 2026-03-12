import logging
import uuid
from app.database import async_session_maker
from app.services.ingestion import get_ingestion_service

logger = logging.getLogger("zunkiree.auto_ingest")


async def run_auto_ingestion(
    customer_id: uuid.UUID,
    site_id: str,
    domains: list[str],
) -> None:
    """
    Background task: auto-crawl allowed domains for a newly created customer.
    Creates its own DB session since the request session is closed by the time this runs.
    """
    logger.info(
        "[AUTO-INGEST] Starting for customer_id=%s site_id=%s domains=%s",
        customer_id, site_id, domains,
    )

    ingestion_service = get_ingestion_service()

    for domain in domains:
        # Normalize domain to https:// URL
        url = domain.strip().rstrip("/")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"

        logger.info("[AUTO-INGEST] Crawling domain=%s for site_id=%s", url, site_id)

        try:
            async with async_session_maker() as db:
                await ingestion_service.ingest_url(
                    db=db,
                    customer_id=customer_id,
                    site_id=site_id,
                    url=url,
                    depth=1,
                    max_pages=20,
                )
                logger.info("[AUTO-INGEST] Completed domain=%s for site_id=%s", url, site_id)
        except Exception as e:
            logger.error(
                "[AUTO-INGEST] Failed domain=%s for site_id=%s error=%s",
                url, site_id, e,
            )
            # Continue to next domain — one failure shouldn't block others

    # After all domains crawled, run site classification
    try:
        from app.services.site_classifier import classify_and_update_customer
        async with async_session_maker() as db:
            await classify_and_update_customer(db, customer_id, site_id)
    except Exception as e:
        logger.error("[AUTO-INGEST] Site classification failed for site_id=%s: %s", site_id, e)

    logger.info("[AUTO-INGEST] Finished all domains for site_id=%s", site_id)
