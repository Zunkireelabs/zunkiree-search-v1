import json
import logging
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func

from app.models import Customer, DocumentChunk, WidgetConfig
from app.models.business_profile import BusinessProfile
from app.config import get_settings
from app.utils.chunking import count_tokens

logger = logging.getLogger("zunkiree.profile_builder")

settings = get_settings()

# High-signal URL/title patterns for content sampling
HIGH_SIGNAL_PATTERNS = [
    "about", "services", "pricing", "price", "faq", "team", "contact",
    "policy", "policies", "return", "refund", "shipping", "menu", "hours",
    "who we are", "what we do", "our story", "products", "catalog",
    "terms", "support", "warranty", "guarantee",
]

# Maximum tokens to sample for LLM extraction
MAX_SAMPLE_TOKENS = 12000

# LLM extraction prompt
EXTRACTION_PROMPT = """You are a business analyst AI. Analyze the following website content and extract a structured business profile.

Return ONLY valid JSON with these exact keys:

{
  "business_description": "2-3 sentence summary of what this business does",
  "business_category": "sub-category within their industry (e.g., clothing, tiles, electronics, boutique_hotel, dental_clinic, law_firm, organic_food)",
  "business_model": "B2C or B2B or B2B2C — detect from content signals",
  "sales_approach": "checkout or catalog or inquiry — determines product display behavior",
  "services_products": ["list of key products or services offered"],
  "pricing_info": "pricing summary or 'Not found' if no pricing visible",
  "policies": {"return": "...", "refund": "...", "shipping": "...", "support": "..."},
  "unique_selling_points": ["list of differentiators or USPs"],
  "target_audience": "who they serve (e.g., young women 18-35, homeowners, B2B distributors)",
  "business_hours": "operating hours or null if not found",
  "location_info": "address/location details or null if not found",
  "team_info": "team/staff info or null if not found",
  "detected_tone": "formal or neutral or friendly — based on website copy style",
  "content_gaps": ["list of important info missing from the website (e.g., pricing, hours, team, contact)"],
  "top_faqs": [{"q": "question", "a": "answer"}, ...up to 10 Q&A pairs that visitors would commonly ask]
}

BUSINESS MODEL DETECTION RULES:
- B2C signals: "add to cart", "buy now", "checkout", consumer pricing, size/color selectors, individual product pages
- B2B signals: "dealers", "distributors", "bulk orders", "request quote", "contact sales", "wholesale", "minimum order"
- B2B2C signals: mix of both, or "find a dealer" + some direct sales

SALES APPROACH RULES:
- "checkout": B2C businesses with online payment/cart (clothing stores, electronics, food delivery)
- "inquiry": B2B businesses where customers request quotes (tiles, construction materials, industrial)
- "catalog": Businesses that showcase products but transactions happen offline (dealerships, real estate)

For top_faqs: Generate helpful Q&A pairs based on the content. Include questions about products/services, pricing, policies, hours, location — anything a website visitor would commonly ask. Answers should be based on the actual content provided.

WEBSITE CONTENT:
"""


class ProfileBuilderService:
    """
    Three-phase pipeline for auto-extracting business profiles:
    1. Smart Content Sampling — prioritize high-signal pages
    2. LLM Extraction — single GPT-4o-mini call for structured extraction
    3. Assembly + Auto-Config + FAQ Ingestion
    """

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def build_profile(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
    ) -> BusinessProfile:
        """
        Build a complete business profile for a tenant.
        Creates or updates the BusinessProfile record.
        """
        # Check for existing profile
        result = await db.execute(
            select(BusinessProfile).where(BusinessProfile.customer_id == customer_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            profile = BusinessProfile(customer_id=customer_id, status="building")
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
        else:
            profile.status = "building"
            profile.updated_at = datetime.utcnow()
            await db.commit()

        try:
            # Phase 1: Smart Content Sampling
            sampled_content = await self._sample_content(db, customer_id)

            if not sampled_content.strip():
                profile.status = "failed"
                profile.updated_at = datetime.utcnow()
                await db.commit()
                logger.warning("[PROFILE] No content to sample for customer_id=%s", customer_id)
                return profile

            # Phase 2: LLM Extraction
            extraction, tokens_used = await self._extract_profile(sampled_content)

            # Phase 3: Assembly + Auto-Config + FAQ Ingestion
            await self._assemble_profile(db, profile, extraction, tokens_used)
            await self._auto_configure_widget(db, customer_id, extraction)
            await self._ingest_faqs(db, customer_id, site_id, extraction)

            profile.status = "completed"
            profile.updated_at = datetime.utcnow()
            await db.commit()

            logger.info(
                "[PROFILE] Completed for customer_id=%s category=%s model=%s approach=%s",
                customer_id, profile.business_category, profile.business_model, profile.sales_approach,
            )

        except Exception as e:
            profile.status = "failed"
            profile.updated_at = datetime.utcnow()
            await db.commit()
            logger.error("[PROFILE] Failed for customer_id=%s: %s", customer_id, e)
            raise

        return profile

    # =========================================================================
    # Phase 1: Smart Content Sampling
    # =========================================================================

    async def _sample_content(self, db: AsyncSession, customer_id: uuid.UUID) -> str:
        """
        Sample high-signal content from document_chunks.
        Prioritizes pages with URLs/titles matching about, services, pricing, etc.
        Caps at ~12,000 tokens.
        """
        # Build a LIKE pattern for high-signal pages
        signal_conditions = []
        for pattern in HIGH_SIGNAL_PATTERNS:
            signal_conditions.append(f"LOWER(source_url) LIKE '%{pattern}%'")
            signal_conditions.append(f"LOWER(source_title) LIKE '%{pattern}%'")

        signal_where = " OR ".join(signal_conditions)

        # Fetch high-signal chunks first
        high_signal_result = await db.execute(
            text(f"""
                SELECT content, source_url, source_title, token_count
                FROM document_chunks
                WHERE customer_id = :cid AND ({signal_where})
                ORDER BY created_at ASC
                LIMIT 50
            """),
            {"cid": str(customer_id)},
        )
        high_signal_chunks = high_signal_result.fetchall()

        # Fetch general/homepage chunks
        general_result = await db.execute(
            text("""
                SELECT content, source_url, source_title, token_count
                FROM document_chunks
                WHERE customer_id = :cid
                ORDER BY created_at ASC
                LIMIT 30
            """),
            {"cid": str(customer_id)},
        )
        general_chunks = general_result.fetchall()

        # Deduplicate and merge (high-signal first)
        seen_content = set()
        sampled_parts = []
        running_tokens = 0

        for chunk in list(high_signal_chunks) + list(general_chunks):
            content = chunk[0]
            if not content or content in seen_content:
                continue

            seen_content.add(content)
            token_count = chunk[3] or count_tokens(content)

            if running_tokens + token_count > MAX_SAMPLE_TOKENS:
                break

            source_label = chunk[2] or chunk[1] or "Page"
            sampled_parts.append(f"[{source_label}]\n{content}")
            running_tokens += token_count

        return "\n\n---\n\n".join(sampled_parts)

    # =========================================================================
    # Phase 2: LLM Extraction
    # =========================================================================

    async def _extract_profile(self, content: str) -> tuple[dict, int]:
        """
        Single LLM call to extract structured business profile.
        Returns (extraction_dict, tokens_used).
        """
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": content},
            ],
            max_tokens=2000,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        raw_text = response.choices[0].message.content.strip()
        tokens_used = response.usage.total_tokens if response.usage else 0

        try:
            extraction = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.error("[PROFILE] Failed to parse LLM JSON response")
            extraction = {}

        return extraction, tokens_used

    # =========================================================================
    # Phase 3: Assembly + Auto-Config + FAQ Ingestion
    # =========================================================================

    async def _assemble_profile(
        self,
        db: AsyncSession,
        profile: BusinessProfile,
        extraction: dict,
        tokens_used: int,
    ) -> None:
        """Populate BusinessProfile fields from extraction dict."""
        profile.business_description = extraction.get("business_description")
        profile.business_category = extraction.get("business_category")
        profile.business_model = extraction.get("business_model")
        profile.sales_approach = extraction.get("sales_approach")
        profile.services_products = json.dumps(extraction.get("services_products", []))
        profile.pricing_info = extraction.get("pricing_info")
        profile.policies = json.dumps(extraction.get("policies", {}))
        profile.unique_selling_points = json.dumps(extraction.get("unique_selling_points", []))
        profile.target_audience = extraction.get("target_audience")
        profile.business_hours = extraction.get("business_hours")
        profile.location_info = extraction.get("location_info")
        profile.team_info = extraction.get("team_info")
        profile.detected_tone = extraction.get("detected_tone")
        profile.content_gaps = json.dumps(extraction.get("content_gaps", []))
        profile.raw_extraction = json.dumps(extraction)
        profile.llm_tokens_used = tokens_used

        # Compose system_prompt_block
        profile.system_prompt_block = self._compose_prompt_block(extraction)

        await db.commit()

    def _compose_prompt_block(self, extraction: dict) -> str:
        """
        Compose a pre-formatted prompt block (200-400 tokens) from extracted fields.
        This gets injected into the system prompt at query time.
        """
        parts = []

        desc = extraction.get("business_description")
        if desc:
            parts.append(f"ABOUT THIS BUSINESS: {desc}")

        category = extraction.get("business_category")
        model = extraction.get("business_model")
        if category or model:
            biz_line = "BUSINESS TYPE:"
            if category:
                biz_line += f" {category}"
            if model:
                biz_line += f" ({model})"
            parts.append(biz_line)

        products = extraction.get("services_products", [])
        if products and isinstance(products, list):
            parts.append(f"KEY OFFERINGS: {', '.join(products[:8])}")

        audience = extraction.get("target_audience")
        if audience:
            parts.append(f"TARGET AUDIENCE: {audience}")

        usps = extraction.get("unique_selling_points", [])
        if usps and isinstance(usps, list):
            parts.append(f"DIFFERENTIATORS: {', '.join(usps[:5])}")

        pricing = extraction.get("pricing_info")
        if pricing and pricing.lower() != "not found":
            parts.append(f"PRICING: {pricing}")

        policies = extraction.get("policies", {})
        if policies and isinstance(policies, dict):
            policy_parts = []
            for key, val in policies.items():
                if val and val.lower() not in ("not found", "none", "n/a", "null"):
                    policy_parts.append(f"{key}: {val}")
            if policy_parts:
                parts.append(f"POLICIES: {'; '.join(policy_parts[:4])}")

        hours = extraction.get("business_hours")
        if hours:
            parts.append(f"HOURS: {hours}")

        location = extraction.get("location_info")
        if location:
            parts.append(f"LOCATION: {location}")

        approach = extraction.get("sales_approach")
        if approach == "inquiry":
            parts.append("SALES MODE: This is a B2B business. When users ask about purchasing, guide them to request a quote or contact sales — do not suggest online checkout.")
        elif approach == "catalog":
            parts.append("SALES MODE: Products are showcased in a catalog. Purchases happen through dealers or in-person — guide users to find a dealer or contact the business directly.")

        if not parts:
            return ""

        return "\n".join(parts)

    async def _auto_configure_widget(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        extraction: dict,
    ) -> None:
        """
        Auto-configure widget settings based on detected business_model and sales_approach.
        Only updates during profile build — not on every query.
        """
        result = await db.execute(
            select(WidgetConfig).where(WidgetConfig.customer_id == customer_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return

        business_model = extraction.get("business_model", "").upper()
        sales_approach = extraction.get("sales_approach", "").lower()
        detected_tone = extraction.get("detected_tone", "").lower()

        # Auto-configure shopping and checkout mode
        if business_model == "B2C" and sales_approach == "checkout":
            config.enable_shopping = True
            config.checkout_mode = "redirect"
        elif business_model == "B2B" and sales_approach == "inquiry":
            config.enable_shopping = True
            config.checkout_mode = "inquiry"
        elif sales_approach == "catalog":
            config.enable_shopping = True
            config.checkout_mode = "redirect"  # Display products, but no direct checkout

        # Auto-set tone if currently default
        if detected_tone in ("formal", "neutral", "friendly") and config.tone == "neutral":
            config.tone = detected_tone

        config.updated_at = datetime.utcnow()
        await db.commit()

        logger.info(
            "[PROFILE] Auto-configured widget: enable_shopping=%s checkout_mode=%s tone=%s",
            config.enable_shopping, config.checkout_mode, config.tone,
        )

    async def _ingest_faqs(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
        extraction: dict,
    ) -> None:
        """
        Ingest auto-generated FAQ pairs via the existing ingestion pipeline.
        """
        faqs = extraction.get("top_faqs", [])
        if not faqs or not isinstance(faqs, list):
            return

        from app.services.ingestion import get_ingestion_service
        ingestion_service = get_ingestion_service()

        ingested_count = 0
        for faq in faqs[:10]:
            if not isinstance(faq, dict):
                continue
            question = faq.get("q", "").strip()
            answer = faq.get("a", "").strip()
            if not question or not answer:
                continue

            try:
                await ingestion_service.ingest_qa(
                    db=db,
                    customer_id=customer_id,
                    site_id=site_id,
                    question=question,
                    answer=answer,
                    source_prefix="Auto-FAQ",
                )
                ingested_count += 1
            except Exception as e:
                logger.warning("[PROFILE] Failed to ingest FAQ '%s': %s", question[:50], e)

        logger.info("[PROFILE] Ingested %d auto-FAQs for site_id=%s", ingested_count, site_id)


# Singleton instance
_profile_builder_service: ProfileBuilderService | None = None


def get_profile_builder_service() -> ProfileBuilderService:
    global _profile_builder_service
    if _profile_builder_service is None:
        _profile_builder_service = ProfileBuilderService()
    return _profile_builder_service
