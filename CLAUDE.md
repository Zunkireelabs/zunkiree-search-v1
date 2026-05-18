# CLAUDE.md — Zunkiree Search (`zunkiree-search-v1`) Repo Window

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Zunkiree Search is a **multi-tenant, AI-powered RAG search + Instagram DM chatbot** embedded via `<script>` tag on customer websites and accessible via Meta's messaging platform. The widget started as single-turn Q&A; the IG chatbot has since grown multi-turn ecommerce capabilities (product search, cart, checkout, order creation).

Currently 5 IG chatbot fixes shipped 2026-05-18 (IG-3, IG-2, IG-6, IG-8, IG-9, IG-5 — see brain folder SESSION-LOG). 218+ backend tests, pytest in `backend/.venv311`. No linter configured.

---

## Multi-Window Workflow

**This repo is operated jointly with the brain folder.** Two Claude Code windows run in parallel:

| Brain folder window (`~/Projects/sadin-stark-brain/`) | This window (`~/Projects/zunkiree-search-v1/`) |
|---|---|
| Writes briefs | Reads briefs, edits code |
| Reviews PR diffs | Opens PRs (base = `stage`) |
| Merges PRs via `gh` | NEVER merges its own PRs |
| Fast-forwards `stage → main` via `gh api PATCH` | Runs psql / DB ops |
| Updates `SESSION-LOG.md` (brain folder) | Smokes locally + reports back |
| Saves cross-session memories | |

**Briefs live at**: `~/Projects/sadin-stark-brain/docs/stella+zunkireesearch/<CONTEXT>-BRIEF.md`. When the brain folder hands off work, expect a brief with: target branch, exact diff, verification steps, traps to watch for. Read the brief end-to-end before editing.

**Session log lives in brain folder**: `~/Projects/sadin-stark-brain/docs/stella+zunkireesearch/SESSION-LOG.md`. **Do not start a new session log in this repo.** The old logs in `docs/archive/` and `docs/archive/session-log/` are frozen historical record.

**When in doubt about scope or approach** — ask the brain folder window for clarification rather than guessing. It has the full strategic context and SESSION-LOG history.

---

## Environments & Branches

| Env | URL | Container | Notes |
|---|---|---|---|
| **Local** | `http://localhost:8000` | uvicorn / docker compose | Backend reads shared staging Supabase by default. Widget dev server on `:5173`. |
| **Stage** | `https://staging-api.zunkireelabs.com` | `zunkiree-search-api-stage` | Auto-deploys on push to `stage` branch. |
| **Prod** | `https://api.zunkireelabs.com` | `zunkiree-search-api` | Auto-deploys on push to `main` via `Deploy to VPS` workflow. |

- **Branches**: both `stage` and `main` active; `stage → main` fast-forwards per-PR after staging verification (opposite of Stella, where `main` promotion is more deliberate).
- **Supabase**: shared project `qzgcowcrtggmttfczbdo` (Mumbai). Single DB for stage + prod. See `[[zunkiree_environment_topology]]` memory.
- **Widget bundle**: live IIFE at `https://zunkiree-search-v1.vercel.app/zunkiree-widget.iife.js`. Auto-deploys from git via Vercel.
- **IG webhook URL**: `https://api.zunkireelabs.com/api/v1/webhooks/meta` (PROD). Stable; do not touch the Meta config. See `[[zunkiree_kasa_ig_webhook_url]]`.

### Deploy lifecycle

```
feature branch → PR → merge to stage → auto-deploys to staging-api.zunkireelabs.com
                                                    ↓
                                       verify on staging
                                                    ↓
                              stage → main (fast-forward via gh api PATCH)
                                                    ↓
                          auto-deploys to api.zunkireelabs.com (prod)
```

Hotfix path (prod down / security): brief → PR direct to `main` → merge fast → watch deploy. Reserve for actual emergencies.

### VPS access

```
ssh vps                                    # SSH alias (uses ~/.ssh/vps_zunkireelabs key, root user)
ssh vps "docker ps"                        # read-only inspection
ssh vps "docker logs --tail 30 zunkiree-search-api"
```

**Hard rule**: do NOT run Claude Code on the VPS. Multiple incidents of silent stale-state deploys (`[[vps_uncommitted_edits_recurring]]`). Pre-flight `ssh vps "git status"` is mandatory before any prod fast-forward. Path on VPS: `/home/zunkireelabs/devprojects/zunkiree-search-v1/`.

---

## Build & Run

### Backend (FastAPI)

```bash
cd backend
python -m venv .venv311
source .venv311/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Tests (218+ in tests/, mostly DM agent + chatbot service coverage)
.venv311/bin/python -m pytest tests/ -q
.venv311/bin/python -m pytest tests/test_dm_agent_prompts.py -v   # IG prompt-content guards
```

Docker:
```bash
docker compose up zunkiree-search-api                       # production stack (Traefik routed)
docker compose --profile backup run zunkiree-backup         # manual DB backup
```

### Widget (React/TypeScript)

```bash
cd widget
npm install
npm run dev       # Vite dev server on :5173
npm run build     # Outputs dist/zunkiree-widget.iife.js (IIFE bundle, Terser minified)
```

---

## Architecture

### Data flow

```
Client website (script tag) → Widget (React IIFE on Vercel CDN)
  → Backend API (FastAPI on VPS)
    → Supabase PostgreSQL (tenant data, query logs, conversations, user profiles)
    → Pinecone (vector embeddings, namespace-per-tenant)
    → OpenAI (embeddings via text-embedding-3-large, LLM via gpt-4o-mini)
    → Meta Send API (IG DM responses)
    → Gmail SMTP (email verification codes)
```

### Multi-tenancy isolation

Every tenant is identified by `customer_id` (UUID) and `site_id` (string). Isolation is enforced at three layers:
- **Pinecone**: each tenant gets its own namespace (`namespace=site_id`)
- **PostgreSQL**: all queries filter by `customer_id` FK
- **CORS**: per-tenant domain allowlist in `domains` table

### Backend structure (`backend/app/`)

- `main.py` — FastAPI app, lifespan (calls `init_db()`), CORS, router registration. All routers mounted at `/api/v1`.
- `config.py` — Pydantic Settings from `.env`. Auto-converts `postgresql://` → `postgresql+asyncpg://` for async Supabase. Access via `get_settings()` (LRU cached).
- `database.py` — Async SQLAlchemy engine + `async_session_maker`. Uses `statement_cache_size=0` for Supabase Supavisor pooler. `init_db()` calls `Base.metadata.create_all`.
- `api/` — Routers: `query.py` (POST /query with SSE streaming), `widget.py` (GET /widget/config/{site_id}), `admin.py` (CRUD + ingestion + stats behind X-Admin-Key), `dashboard.py`, `cart.py`, `orders.py`, `payments.py`, `webhooks.py`, `chatbot_webhooks.py`, `chatbot_admin.py`
- `services/` — Business logic layer:
  - `query.py` — Core RAG pipeline: embed question → Pinecone vector search (top 8) → adaptive top_k by score → optional LLM reranking (0.25 < score < 0.45) → cap at 4000 context tokens → GPT-4o-mini answer → log to `query_logs`
  - `llm.py` — OpenAI abstraction with 24 website-type-aware system prompt templates
  - `agent.py` — Tool-execution loop for the IG chatbot agent (multi-turn, multi-tool). INFO logs every `[AGENT] tool=name args={...}` call. Includes turn-level dedup guard for `add_to_cart` (IG-8 fix, see `[[llm_prompt_mandate_vs_actual_behavior]]`).
  - `chatbot_query.py` — DM agent entry point. Holds `DM_ECOMMERCE_SYSTEM_PROMPT` (LANGUAGE / PRODUCTS / SIZING / QUANTITY / CHECKOUT / POST-CART rules) and `TRANSLATION_SYSTEM_PROMPT` (two-pass localization to Romanized Nepali).
  - `verification.py` — Email verification state machine
  - `personalization.py` — Three-way query classifier (general / personal / lead)
  - `ingestion.py` — Content ingestion: URL crawl, text, file (PDF/DOCX/TXT), Q&A pairs → chunk → embed → dual write to Pinecone + PostgreSQL
  - `vector_store.py` — Pinecone upsert/query/delete with batch size 50
  - `embeddings.py` — OpenAI text-embedding-3-large (3072 dims)
- `models/` — SQLAlchemy ORM: `customer.py`, `widget_config.py`, `domain.py`, `ingestion.py`, `query_log.py`, `verification.py`, `user_profile.py`, `product.py`, `cart.py`, `order.py`, `payment.py`, `chatbot.py`, `chatbot_conversation.py`
- `utils/` — `chunking.py` (token-based text splitting), `crawling.py` (BeautifulSoup URL crawler), `file_parsers.py` (PDF/DOCX/TXT extractors)

### Widget structure (`widget/`)

Single IIFE bundle built with Vite + Terser. CSS is inlined (no separate files). All CSS classes prefixed `zk-` to avoid host page conflicts. Widget reads `data-site-id`, `data-api-url`, `data-mode` from its script tag, creates a `#zunkiree-widget-root` div on body, renders the React app.

The widget is a **single unified bundle** serving all industries (ecommerce, hospitality, generic). Behavior is controlled by `website_type` config from the backend, not separate builds.

---

## Migrations

SQL files in `backend/migrations/`, numbered `001_` through `027_+`. No programmatic runner — migrations are executed manually via `psql`. Migrations are additive only (no DOWN migrations). All are `ALTER TABLE` / `CREATE TABLE` statements.

---

## Key Patterns

### Async everywhere
All database operations, LLM calls, and HTTP requests use `async/await`. Database sessions injected via FastAPI's `Depends(get_db)`.

### SSE streaming
Query responses stream via `StreamingResponse` with `text/event-stream` media type. Each chunk is `data: {json}\n\n`.

### Per-tenant config override
App-wide defaults in `config.py` can be overridden per tenant via `widget_configs` table (e.g., `confidence_threshold`, `tone`, `quick_actions`, `supported_languages`).

### Admin auth
Admin endpoints use `X-Admin-Key` header validated against `settings.api_secret_key`. Master admin auth via `ZUNKIREE_MASTER_ADMIN_TOKEN` — see `[[zunkiree_master_admin_key_set]]`. **Do not regenerate** that token.

### Prompt mandates aren't enforced
LLM "ALWAYS call tool X" prompt rules are NOT reliably honored — IG-9 and IG-5 both surfaced cases where the LLM bypassed the prompt mandate via reasoning. When designing new prompt rules for invariants that MUST hold, also wire enforcement in `agent.py` (turn-level dedup / required-tool gates). See `[[llm_prompt_mandate_vs_actual_behavior]]` and verify on prod via `docker logs zunkiree-search-api | grep '[AGENT]'`.

---

## Instagram DM Chatbot

Auto-replies to Instagram DMs using the agent pipeline (`agent.py` + `chatbot_query.py`). Extensible to Facebook Messenger and WhatsApp via Meta's unified messaging platform.

### How it works

```
Instagram DM → Meta webhook POST /api/v1/webhooks/meta
  → HMAC signature verification (X-Hub-Signature-256)
  → Lookup chatbot_channels table (platform + page_id → tenant)
  → Mark message as seen + show typing indicator
  → Extract attachments (shared posts → URL, unsupported → polite reply)
  → Deduplication via platform_message_id
  → Greeting detection ("hi", "namaste") → instant branded response
  → Feedback signal ("thanks"/"wrong") → update QueryLog, acknowledge
  → Abbreviation expansion ("pp" → "price please")
  → Load conversation history (chatbot_conversations table)
  → Route ecommerce tenants → _process_ecommerce_message → agent.py (tool loop)
  → Send reply via Meta Send API
  → Persist messages + tool-call manifest to chatbot_conversations
```

### Smart features

- **Multi-turn product carousels** — `chatbot_query.py:471` persists a `[products_shown: id1=Name1, id2=Name2]` manifest in conversation history so the next-turn agent can extract real product UUIDs for `add_to_cart` (IG-6 fix, PR #37).
- **Turn-level dedup** — `agent.py:209` skips duplicate `add_to_cart(product_id, size)` calls in the same turn (IG-8 fix, PR #38). Substitutes `get_cart` for the suppressed second call so the LLM sees consistent state.
- **Two-pass translation** — agent emits English; `TRANSLATION_SYSTEM_PROMPT` translates to Romanized Nepali per turn based on `detect_language(user_message)`. LANGUAGE rule (IG-2 fix, PR #36) forbids the agent from switching languages itself.
- **Zero-result follow-up pivot** — when a customer adds a dimension (size, color, price) to a prior zero-result query, the agent acknowledges the specific dimension and pivots to alternatives (IG-5 fix, PR #40). Caveat: LLM achieves this via reasoning, not via the prompted re-search — see sub-finding in `[[llm_prompt_mandate_vs_actual_behavior]]`.
- **Per-tenant abbreviations + supported_languages** via `ChatbotChannel.config` JSONB.
- **Confidence-aware fallback** — uses `_meta.top_score` / `_meta.fallback_triggered` from RAG; low confidence → smart fallback with tenant contact info (saves an LLM call).

### Key files

- `api/chatbot_webhooks.py` — `GET/POST /api/v1/webhooks/meta` (verification + reception + OAuth callback + attachment handling). Synthesizes `Add 'X' to my cart [product_id:abc]` for carousel button postbacks.
- `api/chatbot_admin.py` — Channel CRUD: connect/list/disconnect Instagram accounts per tenant. See `[[zunkiree_chatbot_admin_gotchas]]` for binding gotchas.
- `services/meta_messaging.py` — Meta Send API client, HMAC verification, Fernet token encryption, mark_seen, typing_on.
- `services/chatbot_query.py` — DM agent entrypoint, prompt definitions, multi-turn history + manifest persistence.
- `services/agent.py` — Tool loop. `[AGENT]` INFO logging is load-bearing for IG bug verification.
- `models/chatbot.py` + `models/chatbot_conversation.py` — DB models.

### Database tables

- `chatbot_channels` — Maps tenant Instagram accounts to `customer_id`. Access tokens encrypted with Fernet. `config` JSONB stores `facebook_page_id` for Send API routing + optional `abbreviations` dict.
- `chatbot_conversations` — Persistent multi-turn message history per `platform_sender_id`. Use this for `DELETE WHERE platform_sender_id = '...'` when you need a fresh-LLM-state repro (per Session 30 Part 8 extension pattern).
- `chatbot_message_log` — Audit trail + webhook deduplication via unique `platform_message_id`. `query_log_id` FK links to `query_logs` for analytics.

### Meta App Setup

- **App ID**: 2104437347081359 (ZunkireeSearch) — see `[[zunkiree_meta_app_mapping]]` for the full IG ↔ app mapping
- **Webhook URL**: `https://api.zunkireelabs.com/api/v1/webhooks/meta`
- **Verify token**: `zunkiree_meta_webhook_2026`
- **HMAC**: if you see `Signature mismatch` storms, it's usually App Secret drift requiring dashboard Reset, not a regression. See `[[zunkiree_meta_hmac_recurring]]`.

---

## Environment Variables

Required in `backend/.env`:
- `OPENAI_API_KEY`, `PINECONE_API_KEY`, `PINECONE_HOST`, `DATABASE_URL` — core services
- `API_SECRET_KEY` — admin endpoint auth
- `ZUNKIREE_MASTER_ADMIN_TOKEN` — master admin endpoint auth (see `[[zunkiree_master_admin_key_set]]`)
- `STELLA_BACKEND_CREDENTIALS_ENCRYPTION_KEY` — Fernet key for encrypting tenant backend creds. **Must match across stage + prod.** Do not regenerate.
- `ALLOWED_ORIGINS` — comma-separated CORS origins
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` — email verification
- `META_APP_SECRET` — Meta App Secret (from App Dashboard → App settings → Basic)
- `META_VERIFY_TOKEN` — webhook verification token (must match Meta webhook config)
- `CHATBOT_ENCRYPTION_KEY` — Fernet key for encrypting page access tokens at rest
- `WIDGET_SCRIPT_BASE_URL` — base URL for the IIFE bundle (per-env; see `[[zunkiree_widget_bundle_url]]`)
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` — payments (optional)

Defaults: `LLM_MODEL=gpt-4o-mini`, `EMBEDDING_MODEL=text-embedding-3-large`, `EMBEDDING_DIMENSIONS=3072`, `CONFIDENCE_THRESHOLD=0.25`, `LLM_TEMPERATURE=0.3`.

---

## Documentation

- `docs/README.md` — folder-structure index; explains where session log lives (brain folder is single source of truth)
- `docs/reference/architecture.md` — full architecture writeup
- `docs/reference/api-spec.md` — API contract
- `docs/reference/database-schema.md` — schema reference
- `docs/reference/widget-spec.md` + `widget-style-guide.md` — widget contract + style guide
- `docs/reference/llm-abstraction.md` — LLM service contract
- `docs/reference/developer-workflow.md` — local dev + PR workflow
- `docs/reference/deployment-plan.md` — historical deployment plan (some URLs may be stale; cross-check against env table above)
- `docs/archive/` — stale/historical material (old roadmap, TODO, session logs from pre-brain-folder era)
- `.claude/ZUNKIREE_SEARCH_CLAUDE_OPERATING_SYSTEM.md` — phase discipline + operating rules (verify currency before applying; some framing predates the current operating mode)

---

## Hard rules

- **No Claude Code on the VPS.** Multiple incidents of silent stale-state deploys (`[[vps_uncommitted_edits_recurring]]`). Pre-flight `ssh vps "git status"` before any prod fast-forward.
- **No regenerating `STELLA_BACKEND_CREDENTIALS_ENCRYPTION_KEY` or `ZUNKIREE_MASTER_ADMIN_TOKEN`.** Rotation is coordinated.
- **No new session log in this repo.** Brain folder owns the log.
- **No merging your own PRs.** Brain folder reviews + merges.
- **Stage → main fast-forwards per-PR** — but always pre-flight `ssh vps "git status"` first.
