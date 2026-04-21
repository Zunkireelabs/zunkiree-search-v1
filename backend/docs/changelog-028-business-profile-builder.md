# Changelog: Auto Business Profile Builder

**Date:** 2026-04-21
**Migration:** 028
**Commit:** `a5b17a2`
**Branch:** `feature/rag-quality-and-widget-improvements` → merged to `main`

---

## Summary

Adds an automatic business profile builder that extracts structured business intelligence from crawled website content. On every query, the extracted profile is injected into the LLM system prompt so the chatbot answers as a domain expert from day one — no manual configuration needed.

---

## How It Works

```
Customer created → domains crawled → site classified → profile builder runs
  → Samples ~12K tokens from high-signal pages (about, pricing, FAQ, services)
  → Single GPT-4o-mini call extracts structured business profile + 10 auto-FAQs
  → Composes system_prompt_block (200-400 tokens of business intelligence)
  → Auto-configures widget settings (enable_shopping, checkout_mode, tone)
  → Ingests up to 10 auto-generated FAQ pairs into the embedding pipeline
  → Saves profile (status=completed)

On every query:
  → QueryService fetches BusinessProfile (indexed lookup, ~1ms)
  → system_prompt_block injected into LLM system prompt
  → Chatbot answers with business-specific context
```

---

## Files Changed (10 total)

### New Files (3)

| File | Purpose |
|------|---------|
| `backend/app/models/business_profile.py` | SQLAlchemy ORM model — `BusinessProfile` table with 20+ fields: business_description, business_category, business_model (B2C/B2B/B2B2C), sales_approach (checkout/catalog/inquiry), services_products, policies, USPs, target_audience, detected_tone, content_gaps, system_prompt_block, status tracking |
| `backend/app/services/profile_builder.py` | Three-phase pipeline: (1) Smart content sampling from high-signal pages capped at 12K tokens, (2) Single GPT-4o-mini call with JSON extraction, (3) Assembly into system_prompt_block + widget auto-config + FAQ ingestion |
| `backend/migrations/028_create_business_profiles.sql` | CREATE TABLE business_profiles with customer_id FK (UNIQUE, CASCADE), all profile fields, indexes on customer_id and status. Safe to re-run (IF NOT EXISTS) |

### Modified Files (7)

| File | What Changed |
|------|-------------|
| `backend/app/models/__init__.py` | Added `BusinessProfile` import and `__all__` entry |
| `backend/app/models/customer.py` | Added `business_profile` 1:1 relationship with cascade delete |
| `backend/app/services/llm.py` | Added `{business_context}` placeholder in SYSTEM_PROMPT_TEMPLATE, added `business_context: str | None = None` param to `generate_answer()` and `generate_answer_stream()` |
| `backend/app/services/query.py` | Added `_get_business_profile()` helper, updated `_build_llm_params()` to accept profile and include `business_context` key, wired profile fetch into `process_query()` and `process_query_stream()` |
| `backend/app/services/auto_ingest.py` | Added profile build step after site classification (non-blocking — failure doesn't crash ingestion) |
| `backend/app/services/ingestion.py` | Added `source_prefix: str = "QA"` param to `ingest_qa()` — auto-FAQs use "Auto-FAQ" prefix for traceability |
| `backend/app/api/admin.py` | Added 3 admin endpoints for profile management |

---

## API Endpoints Added

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/build-profile/{site_id}` | Trigger profile build for a single tenant (runs in background) |
| POST | `/admin/build-profiles/all` | Backfill profiles for all active customers (runs in background) |
| GET | `/admin/profile/{site_id}` | View profile status and extracted data for a tenant |

All endpoints require `X-Admin-Key` header.

---

## Database Changes

### New Table: `business_profiles`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Primary key |
| customer_id | UUID (FK, UNIQUE) | References customers(id) ON DELETE CASCADE |
| business_description | TEXT | 2-3 sentence summary |
| business_category | VARCHAR(100) | Sub-category (e.g., clothing, dental_clinic) |
| business_model | VARCHAR(20) | B2C / B2B / B2B2C |
| sales_approach | VARCHAR(20) | checkout / catalog / inquiry |
| services_products | TEXT (JSON) | Array of key offerings |
| pricing_info | TEXT | Pricing summary |
| policies | TEXT (JSON) | Return, refund, shipping, support policies |
| unique_selling_points | TEXT (JSON) | Array of differentiators |
| target_audience | TEXT | Who they serve |
| business_hours | TEXT | Operating hours |
| location_info | TEXT | Address/location |
| team_info | TEXT | Team/staff info |
| detected_tone | VARCHAR(20) | formal / neutral / friendly |
| content_gaps | TEXT (JSON) | Array of missing info |
| raw_extraction | TEXT (JSON) | Full LLM response for debugging |
| system_prompt_block | TEXT | Pre-composed prompt block injected at query time |
| status | VARCHAR(20) | pending / building / completed / failed |
| llm_tokens_used | INTEGER | Token usage tracking |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

**Indexes:** `idx_business_profiles_customer_id`, `idx_business_profiles_status`

---

## Extracted Fields

The profile builder extracts the following from website content via a single GPT-4o-mini call:

- **Business description** — what the business does
- **Category** — industry sub-category
- **Business model** — B2C, B2B, or B2B2C (detected from cart/checkout/quote signals)
- **Sales approach** — checkout, catalog, or inquiry
- **Products/services** — list of key offerings
- **Pricing** — pricing summary if visible
- **Policies** — return, refund, shipping, support
- **USPs** — differentiators
- **Target audience** — who they serve
- **Tone** — formal, neutral, or friendly (auto-applied to widget)
- **Content gaps** — what's missing from the website
- **Auto-FAQs** — up to 10 Q&A pairs ingested into the embedding pipeline

---

## Widget Auto-Configuration

Based on extracted profile, the builder automatically updates widget settings:

| Detected | Widget Change |
|----------|--------------|
| B2C + checkout | `enable_shopping=true`, `checkout_mode=redirect` |
| B2B + inquiry | `enable_shopping=true`, `checkout_mode=inquiry` |
| catalog | `enable_shopping=true`, `checkout_mode=redirect` |
| Detected tone differs from default | `tone` updated to match website copy style |

---

## Backward Compatibility

Fully backward compatible:
- Customers without a profile get `business_context=""` — identical behavior to before
- Profile build failures don't crash ingestion (non-blocking)
- To disable: don't run backfill; new profiles won't affect existing behavior
- To rollback: `DROP TABLE IF EXISTS business_profiles;` and redeploy previous code

---

## Deployment

- **CI/CD:** Auto-deployed via GitHub Actions on push to `main`
- **Migration:** Applied automatically by `scripts/migrate.sh`
- **Backfill:** `POST /admin/build-profiles/all` — completed for 8 customers
- **No new env vars required** — uses existing `OPENAI_API_KEY` and `DATABASE_URL`
