# Changelog: Similar Clients — Template-Based Customer Onboarding

**Date:** 2026-04-21
**Migration:** 029
**Depends on:** 028 (Business Profile Builder)

---

## Summary

When onboarding a new client, the admin dashboard now auto-detects similar existing clients (by website type) and lets the admin clone their full configuration as a starting template. This saves setup time for clients in the same industry (e.g., multiple clothing B2C stores). The manual clone overrides the auto-generated profile.

---

## Flow

```
Admin creates customer (name, site_id, domains, website_type)
  → API returns success
  → Frontend auto-fetches similar clients by website_type
  → Shows matching clients with preview (category, tone, shopping config)
  → Admin clicks "Use as Template" on one OR clicks "Skip"
  → If template selected: clone widget config + business profile + lock profile
  → Auto-ingestion still runs, but profile builder skips locked profiles
```

---

## Files Changed (5)

### New File

| File | Purpose |
|------|---------|
| `backend/migrations/029_add_profile_locked.sql` | Adds `profile_locked BOOLEAN DEFAULT FALSE` to `business_profiles` table |

### Modified Files

| File | What Changed |
|------|-------------|
| `backend/app/models/business_profile.py` | Added `profile_locked` field (Boolean, default False) |
| `backend/app/services/profile_builder.py` | Added guard in `build_profile()` — skips auto-build when `profile_locked=True` |
| `backend/app/api/admin.py` | Added 2 endpoints: `GET /admin/similar-clients`, `POST /admin/customers/{site_id}/clone-from/{template_site_id}`. Added `profile_locked` to `GET /admin/profile/{site_id}` response |
| `admin/index.html` | Added similar clients panel UI (HTML + CSS + JS) shown after customer creation |

---

## API Endpoints Added

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/similar-clients?website_type={type}&limit=10` | Find existing clients with matching website_type. Returns name, site_id, business_category, business_model, sales_approach, detected_tone, enable_shopping, checkout_mode, business_description |
| POST | `/admin/customers/{site_id}/clone-from/{template_site_id}` | Clone full widget config + business profile from template client to new client. Sets `profile_locked=True` to prevent auto-profile from overwriting |

Both endpoints require `X-Admin-Key` header.

---

## Database Changes

### Migration 029: `business_profiles` table

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `profile_locked` | BOOLEAN | FALSE | When TRUE, `profile_builder.build_profile()` skips this customer — preserving the cloned template |

---

## What Gets Cloned

| Source | Cloned Fields | NOT Cloned |
|--------|--------------|------------|
| **WidgetConfig** | tone, primary_color, placeholder_text, welcome_message, fallback_message, allowed_topics, max_response_length, show_sources, show_suggestions, quick_actions, confidence_threshold, enable_identity_verification, identity_custom_fields, lead_intents, contact_email, contact_phone, supported_languages, enable_shopping, checkout_mode, shipping_countries | brand_name (keeps new customer's name), stripe_account_id (null), payment_enabled (false) |
| **BusinessProfile** | All extracted fields, system_prompt_block, detected_tone, content_gaps | customer_id, id, timestamps. Sets profile_locked=True, status=completed |

---

## Race Condition Handling

Auto-ingestion runs in background after customer creation. If admin clones a template:
- **Before auto-profile finishes:** Clone sets `profile_locked=True`. When `build_profile()` runs later, it sees the lock and skips.
- **After auto-profile finishes:** Clone overwrites the auto-generated profile with template data and sets `profile_locked=True`.

Both scenarios are safe.

---

## Admin UI Behavior

1. Admin fills out the Create Customer form and submits
2. On success, if a website_type was selected, the panel auto-queries `GET /admin/similar-clients`
3. Matching clients appear as cards showing: name, site_id, category, business model, tone, shopping status
4. Admin clicks "Use as Template" → calls clone endpoint → success toast
5. "Skip" link dismisses the panel (auto-detected settings from profile builder will be used instead)

---

## Backward Compatibility

- Fully backward compatible — existing customers have `profile_locked=FALSE` by default
- The similar clients panel only appears when matches exist; otherwise the flow is unchanged
- Profile builder behavior is identical for non-locked profiles
