# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Zunkiree Search is a **multi-tenant, AI-powered RAG search widget** embedded via `<script>` tag on customer websites. It is a single-turn Q&A system — not a chatbot, not a multi-agent platform, not a workflow engine.

**Current phase: Phase 1 — Product Validation.** Do not introduce conversation memory, analytics dashboards, billing systems, self-serve UI, or architectural refactors. See `.claude/ZUNKIREE_SEARCH_CLAUDE_OPERATING_SYSTEM.md` for full phase discipline rules.

## Build & Run

### Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Docker:
```bash
docker compose up zunkiree-search-api    # production (Traefik routed)
docker compose --profile backup run zunkiree-backup  # manual DB backup
```

### Widget (React/TypeScript)

```bash
cd widget
npm install
npm run dev       # Vite dev server on :5173
npm run build     # Outputs dist/zunkiree-widget.iife.js (IIFE bundle)
```

### No tests exist yet. No linter is configured.

## Architecture

### Data flow

```
Client website (script tag) → Widget (React IIFE on Vercel CDN)
  → Backend API (FastAPI on VPS/Railway)
    → Supabase PostgreSQL (tenant data, query logs, user profiles)
    → Pinecone (vector embeddings, namespace-per-tenant)
    → OpenAI (embeddings via text-embedding-3-large, LLM via gpt-4o-mini)
    → Gmail SMTP (email verification codes)
```

### Multi-tenancy isolation

Every tenant is identified by `customer_id` (UUID) and `site_id` (string). Isolation is enforced at three layers:
- **Pinecone**: Each tenant gets its own namespace (`namespace=site_id`)
- **PostgreSQL**: All queries filter by `customer_id` FK
- **CORS**: Per-tenant domain allowlist in `domains` table

### Backend structure (`backend/app/`)

- `main.py` — FastAPI app, lifespan (calls `init_db()`), CORS, router registration. All routers mounted at `/api/v1`.
- `config.py` — Pydantic Settings from `.env`. Auto-converts `postgresql://` to `postgresql+asyncpg://` for async Supabase. Access via `get_settings()` (LRU cached).
- `database.py` — Async SQLAlchemy engine + session. Uses `statement_cache_size=0` for Supabase Supavisor pooler. `init_db()` calls `Base.metadata.create_all`.
- `api/` — Routers: `query.py` (POST /query with SSE streaming), `widget.py` (GET /widget/config/{site_id}), `admin.py` (CRUD, ingestion, stats behind X-Admin-Key), `dashboard.py`, `cart.py`, `orders.py`, `payments.py`, `webhooks.py`
- `services/` — Business logic layer:
  - `query.py` — Core RAG pipeline: embed question → Pinecone vector search (top 8) → adaptive top_k based on score → optional LLM reranking (0.25 < score < 0.45) → cap at 4000 context tokens → GPT-4o-mini answer → log to query_logs
  - `llm.py` — OpenAI abstraction with 24 website-type-aware system prompt templates
  - `verification.py` — Email verification state machine: anonymous → email_requested → code_sent → code_verified → name_requested → fields_requested → verified
  - `personalization.py` — Three-way query classifier (general / personal / lead) determining whether identity verification is needed
  - `ingestion.py` — Content ingestion: URL crawl, text, file (PDF/DOCX/TXT), Q&A pairs → chunk → embed → dual write to Pinecone + PostgreSQL
  - `vector_store.py` — Pinecone upsert/query/delete with batch size 50
  - `embeddings.py` — OpenAI text-embedding-3-large (3072 dimensions)
- `models/` — SQLAlchemy ORM: `customer.py`, `widget_config.py`, `domain.py`, `ingestion.py` (IngestionJob + DocumentChunk), `query_log.py`, `verification.py`, `user_profile.py`, `product.py`, `cart.py`, `order.py`, `payment.py`, `room.py`, `wishlist.py`
- `utils/` — `chunking.py` (token-based text splitting), `crawling.py` (BeautifulSoup URL crawler), `file_parsers.py` (PDF/DOCX/TXT extractors)

### Widget structure (`widget/`)

Single IIFE bundle built with Vite + Terser. CSS is inlined (no separate files). All CSS classes prefixed `zk-` to avoid host page conflicts. The widget reads `data-site-id`, `data-api-url`, and `data-mode` from its script tag, creates a `#zunkiree-widget-root` div appended to body, and renders the React app.

The widget is a **single unified bundle** serving all industries (ecommerce, hospitality, generic). Behavior is controlled by `website_type` config from the backend, not separate builds.

### Infrastructure

- **VPS**: Docker Compose + Traefik reverse proxy on external `hosting` network. SSL via Let's Encrypt ACME.
- **Widget CDN**: Vercel (auto-deploys from git). `vercel.json` sets `Cache-Control: public, max-age=0, must-revalidate` and `Access-Control-Allow-Origin: *`.
- **Backend hosting**: VPS (Docker) at `api.zunkireelabs.com`. SSH: `anish@94.136.189.213`. Project path: `/home/zunkireelabs/devprojects/zunkiree-search-v1`.

## Migrations

SQL files in `backend/migrations/`, numbered `001_` through `023_`. No programmatic runner exists — migrations are executed manually via `psql`. There are duplicate numbers: two `020_*.sql` and two `021_*.sql` files.

Migrations are additive only (no DOWN migrations). All are `ALTER TABLE` / `CREATE TABLE` statements.

## Key Patterns

### Async everywhere
All database operations, LLM calls, and HTTP requests use `async/await`. Database sessions are injected via FastAPI's `Depends(get_db)`.

### SSE streaming
Query responses stream via `StreamingResponse` with `text/event-stream` media type. Each chunk is `data: {json}\n\n`.

### Per-tenant config override
App-wide defaults in `config.py` can be overridden per tenant via `widget_configs` table (e.g., `confidence_threshold`, `tone`, `quick_actions`).

### Admin auth
Admin endpoints use `X-Admin-Key` header validated against `settings.api_secret_key`.

## Instagram DM Chatbot

Auto-replies to Instagram DMs using the same RAG pipeline as the search widget. Extensible to Facebook Messenger and WhatsApp (all use Meta's unified messaging platform).

### How it works

```
Instagram DM → Meta webhook POST /api/v1/webhooks/meta
  → HMAC signature verification
  → Lookup chatbot_channels table (platform + page_id → tenant)
  → Mark message as seen (blue ticks) + show typing indicator
  → Deduplication via platform_message_id
  → Load conversation history (last 10 messages from DB)
  → Call QueryService.process_query() (same RAG pipeline as widget)
  → Refine answer through conversational LLM (always, not just multi-turn)
  → Send reply via Meta Send API (with inline suggestions as text)
  → Persist messages to chatbot_conversations
```

### Key files

- `api/chatbot_webhooks.py` — `GET/POST /api/v1/webhooks/meta` (webhook verification + message reception + OAuth callback handler)
- `api/chatbot_admin.py` — Channel CRUD: connect/list/disconnect Instagram accounts per tenant
- `services/meta_messaging.py` — Meta Send API client, HMAC verification, Fernet token encryption, mark_seen, typing_on
- `services/chatbot_conversation.py` — Persistent conversation store (PostgreSQL-backed, 7-day TTL)
- `services/chatbot_query.py` — Wraps existing RAG pipeline with conversational LLM refinement (does NOT modify QueryService)
- `models/chatbot.py` — ChatbotChannel, ChatbotConversation, ChatbotMessageLog

### Database tables

- `chatbot_channels` — Maps tenant Instagram accounts to customer_id. Access tokens encrypted with Fernet. `config` JSONB stores `facebook_page_id` for Instagram Send API routing.
- `chatbot_conversations` — Persistent multi-turn message history per sender (user + assistant messages).
- `chatbot_message_log` — Audit trail + webhook deduplication via unique `platform_message_id`.

### Connecting a tenant's Instagram

The Instagram account must be a Professional (Business) account linked to a Facebook Page.

```bash
# 1. Create the channel (platform_page_id = Instagram user ID from Meta Dashboard)
curl -X POST https://api.zunkireelabs.com/api/v1/admin/chatbot/channels \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: <admin_key>" \
  -d '{"site_id":"<tenant>","platform":"instagram","platform_page_id":"<ig_user_id>","page_access_token":"<page_access_token>","channel_name":"@handle"}'

# 2. Set the Facebook Page ID in channel config (required for Send API)
# This must be done via DB: UPDATE chatbot_channels SET config = '{"facebook_page_id":"<fb_page_id>"}' WHERE platform_page_id = '<ig_user_id>';
```

**Token generation:** Use Graph API Explorer → select app → Get Page Access Token → select the Facebook Page linked to the Instagram account. Requires permissions: `pages_show_list`, `pages_messaging`, `instagram_basic`, `instagram_manage_messages`.

### Meta App Setup

- **App ID**: 2104437347081359 (ZunkireeSearch)
- **Instagram App ID**: 2067985003771014 (ZunkireeSearch-IG)
- **Webhook URL**: `https://api.zunkireelabs.com/api/v1/webhooks/meta`
- **Verify token**: `zunkiree_meta_webhook_2026`
- **Privacy Policy**: `https://zunkiree-legal.vercel.app/privacy-policy`
- **Products configured**: Webhooks, Instagram, Messenger

### Webhook subscription (3 places must be configured)

1. **Webhooks product** → Select "Instagram" → `messages` field must be Subscribed
2. **Instagram → API setup with Instagram login** → "1. Generate access tokens" → Webhook Subscription toggle must be ON for the connected account (requires generating token through Meta's UI)
3. **Messenger → Instagram settings** → Page must be added with `messages` webhook subscription. This is the step that actually enables Instagram DM webhooks.

### App Review status

- **App Mode**: Live (privacy policy required)
- **`instagram_manage_messages`**: Not yet approved. Without approval, chatbot can only reply to app admins and accepted Instagram testers. Testers must accept invitations via Instagram → Settings → Apps and Websites.
- To submit: App Review → Permissions and Features → request `instagram_manage_messages`

### Deployment notes (VPS)

After code changes, rebuild and restart on VPS (`ssh anish@94.136.189.213`):
```bash
cd /home/zunkireelabs/devprojects/zunkiree-search-v1
git pull origin main
docker compose build zunkiree-search-api
docker compose up -d --force-recreate zunkiree-search-api
```

Env vars must be added to `backend/.env` on VPS AND restarted for changes to take effect.

## Environment Variables

Required in `backend/.env`:
- `OPENAI_API_KEY`, `PINECONE_API_KEY`, `PINECONE_HOST`, `DATABASE_URL` — core services
- `API_SECRET_KEY` — admin endpoint auth
- `ALLOWED_ORIGINS` — comma-separated CORS origins
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` — email verification
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` — payments (optional)
- `META_APP_SECRET` — Meta App Secret (from App Dashboard → App settings → Basic)
- `META_VERIFY_TOKEN` — webhook verification token (must match value in Meta webhook config)
- `CHATBOT_ENCRYPTION_KEY` — Fernet key for encrypting page access tokens at rest

Defaults: `LLM_MODEL=gpt-4o-mini`, `EMBEDDING_MODEL=text-embedding-3-large`, `EMBEDDING_DIMENSIONS=3072`, `CONFIDENCE_THRESHOLD=0.25`, `LLM_TEMPERATURE=0.3`
