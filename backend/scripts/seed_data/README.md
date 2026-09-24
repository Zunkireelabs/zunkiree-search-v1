# Tenant quick-facts data

One JSON file per tenant, loaded by `scripts/seed_tenant_quick_facts.py`:

```
.venv311/bin/python -m scripts.seed_tenant_quick_facts <site_id> scripts/seed_data/<site_id>_quick_facts.json
```

See that script's module docstring for the JSON shape. To onboard a new
clinic (e.g. Healthy Smile), add a new `<site_id>_quick_facts.json` here and
run the script — no code change.

## `dental_city_quick_facts.json`

Ported as-is from the old `seed_dental_city_quick_facts.py` (ZUNKIREE-FAST-FACTS-BRIEF
§1.4, ZUNKIREE-FAST-FACTS-NEPALI-BRIEF §1) when that script was replaced by
the generic writer. Content unchanged; the provenance notes that used to
live in that script's docstring:

- Sourced from what's already ingested into dental-city's Pinecone namespace
  / `document_chunks` (read via a DB query, not re-derived) — the QA chunks
  and the "Dental City Services" chunk. No prices were found in the
  ingested content (dental-city's prices live in ClinicMD's `treatments`
  table and are already served fast, without embeddings, by the
  `list_services` tool — nothing to seed here for that).
- ClinicMD's `branches.open_time`/`close_time` are `NULL` for dental-city
  (verified live against the ClinicMD Supabase project on 2026-09-23), so
  this is not a second copy of data ClinicMD already owns
  (S4-TENANT-CONFIG-BRIEF finding #3) — it's the only copy.
  `clinic_tools._hours_from_clinicmd_branch` still prefers ClinicMD's value
  over this one if that ever changes.
- Nepali keywords (Devanagari): dental-city's voice agent defaults to
  Nepali, so English-only keywords meant the fast-path never fired for most
  real calls (ZUNKIREE-FAST-FACTS-NEPALI-BRIEF §0). No `answer_ne` variant —
  verified live that `_search_knowledge`'s caller (`clinic_agent.py`'s
  LANGUAGE-directive system prompt) already re-composes the final reply in
  the visitor's language from whatever English tool content it's given,
  identically whether that content came from a quick fact or a RAG chunk.
  These Nepali keyword lists use standard, widely-known vocabulary but have
  **not** been checked against a native speaker's ear for how ElevenLabs'
  ASR actually transcribes casual spoken Nepali (the caution
  `NEPALI-QUALITY-FINDINGS.md` already raises generally) — flag before
  wider rollout to a tenant whose spoken-language mix differs.
