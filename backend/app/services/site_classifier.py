import json
import logging
import re
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models import Customer, DocumentChunk

logger = logging.getLogger("zunkiree.site_classifier")

# Website type constants
WEBSITE_TYPES = ["ecommerce", "blog", "saas", "service", "portfolio", "restaurant", "other"]

# --- Heuristic signal patterns ---

ECOMMERCE_SIGNALS = [
    # Schema.org / JSON-LD
    re.compile(r'"@type"\s*:\s*"Product"', re.IGNORECASE),
    re.compile(r'"@type"\s*:\s*"Offer"', re.IGNORECASE),
    # Open Graph
    re.compile(r'og:type.*product', re.IGNORECASE),
    # Cart/checkout URLs
    re.compile(r'/cart\b', re.IGNORECASE),
    re.compile(r'/checkout\b', re.IGNORECASE),
    re.compile(r'/bag\b', re.IGNORECASE),
    # Price patterns
    re.compile(r'[\$\€\£\¥][\s]?\d+[\.,]?\d*'),
    re.compile(r'Rs\.?\s?\d+', re.IGNORECASE),
    re.compile(r'NPR\s?\d+', re.IGNORECASE),
    # Platform identifiers
    re.compile(r'cdn\.shopify\.com', re.IGNORECASE),
    re.compile(r'woocommerce', re.IGNORECASE),
    re.compile(r'bigcommerce', re.IGNORECASE),
    re.compile(r'magento', re.IGNORECASE),
    # Add-to-cart patterns
    re.compile(r'add[_-]?to[_-]?cart', re.IGNORECASE),
    re.compile(r'add to bag', re.IGNORECASE),
]

BLOG_SIGNALS = [
    re.compile(r'/blog\b', re.IGNORECASE),
    re.compile(r'/post/', re.IGNORECASE),
    re.compile(r'/article/', re.IGNORECASE),
    re.compile(r'<article', re.IGNORECASE),
    re.compile(r'published\s+on\s+\d', re.IGNORECASE),
    re.compile(r'reading time', re.IGNORECASE),
    re.compile(r'author:', re.IGNORECASE),
]

SAAS_SIGNALS = [
    re.compile(r'/pricing\b', re.IGNORECASE),
    re.compile(r'/features\b', re.IGNORECASE),
    re.compile(r'/signup\b', re.IGNORECASE),
    re.compile(r'/sign-up\b', re.IGNORECASE),
    re.compile(r'/demo\b', re.IGNORECASE),
    re.compile(r'free trial', re.IGNORECASE),
    re.compile(r'start free', re.IGNORECASE),
    re.compile(r'/api\b', re.IGNORECASE),
]

RESTAURANT_SIGNALS = [
    re.compile(r'/menu\b', re.IGNORECASE),
    re.compile(r'reservation', re.IGNORECASE),
    re.compile(r'opening hours', re.IGNORECASE),
    re.compile(r'delivery', re.IGNORECASE),
    re.compile(r'dine[- ]?in', re.IGNORECASE),
    re.compile(r'cuisine', re.IGNORECASE),
]

SIGNAL_MAP = {
    "ecommerce": ECOMMERCE_SIGNALS,
    "blog": BLOG_SIGNALS,
    "saas": SAAS_SIGNALS,
    "restaurant": RESTAURANT_SIGNALS,
}

# Minimum signals needed for confident classification
MIN_STRONG_SIGNALS = 3


def classify_from_content(page_contents: list[str]) -> str:
    """
    Classify website type from crawled page content using heuristics.
    Returns the website type string.
    """
    combined_text = "\n".join(page_contents[:20])  # Limit to first 20 pages

    scores: dict[str, int] = {wtype: 0 for wtype in SIGNAL_MAP}

    for wtype, patterns in SIGNAL_MAP.items():
        for pattern in patterns:
            if pattern.search(combined_text):
                scores[wtype] += 1

    # Find the type with the most signals
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score >= MIN_STRONG_SIGNALS:
        logger.info("[CLASSIFY] Heuristic classification: %s (score=%d)", best_type, best_score)
        return best_type

    # If no clear winner, try LLM classification
    return _llm_classify_fallback(combined_text[:3000], scores)


def _llm_classify_fallback(sample_text: str, heuristic_scores: dict[str, int]) -> str:
    """
    Fallback: if heuristics are ambiguous, use the highest scoring type
    or default to 'service'. LLM call is avoided for cost — we use
    the heuristic scores as a tiebreaker.
    """
    best_type = max(heuristic_scores, key=heuristic_scores.get)
    best_score = heuristic_scores[best_type]

    if best_score > 0:
        logger.info("[CLASSIFY] Weak heuristic classification: %s (score=%d)", best_type, best_score)
        return best_type

    # No signals at all — default to 'service'
    logger.info("[CLASSIFY] No signals detected, defaulting to 'service'")
    return "service"


async def classify_and_update_customer(
    db: AsyncSession,
    customer_id: uuid.UUID,
    site_id: str,
) -> str:
    """
    Classify website type from crawled content and update the customer record.
    Returns the classified website type.
    """
    # Fetch crawled content from document_chunks
    result = await db.execute(
        select(DocumentChunk.content).where(
            DocumentChunk.customer_id == customer_id,
        ).limit(50)
    )
    contents = [row[0] for row in result.fetchall()]

    if not contents:
        logger.info("[CLASSIFY] No content found for site_id=%s, defaulting to 'other'", site_id)
        website_type = "other"
    else:
        website_type = classify_from_content(contents)

    # Update customer record
    await db.execute(
        text("UPDATE customers SET website_type = :wtype WHERE id = :cid"),
        {"wtype": website_type, "cid": str(customer_id)},
    )
    await db.commit()

    logger.info("[CLASSIFY] site_id=%s classified as: %s", site_id, website_type)
    return website_type
