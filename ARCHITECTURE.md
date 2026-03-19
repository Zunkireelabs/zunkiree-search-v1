# Zunkiree Search — System Architecture

## Overview

Zunkiree Search is a **multi-tenant, AI-powered search widget** that customers embed on their websites. It provides RAG-based Q&A, identity verification, lead capture, and personalized responses — all from a single embeddable `<script>` tag.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        END USER'S BROWSER                          │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Customer Website (e.g., dev-web.admizzeducation.com)        │   │
│  │                                                              │   │
│  │  ┌────────────────────────────────────────────────────────┐  │   │
│  │  │  Zunkiree Widget (IIFE bundle)                         │  │   │
│  │  │  React 18 + TypeScript + Vite                          │  │   │
│  │  │                                                        │  │   │
│  │  │  ┌──────────────┐     ┌─────────────────────────────┐  │  │   │
│  │  │  │ CollapsedBar │ ──► │ ExpandedPanel               │  │  │   │
│  │  │  │ (card view)  │     │ (full conversation surface) │  │  │   │
│  │  │  └──────────────┘     └─────────────────────────────┘  │  │   │
│  │  └───────────────────────────┬────────────────────────────┘  │   │
│  └──────────────────────────────┼───────────────────────────────┘   │
└─────────────────────────────────┼───────────────────────────────────┘
                                  │ HTTPS
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         VPS (Docker + Traefik)                      │
│                                                                     │
│  Traefik reverse proxy ─── SSL termination ─── api.zunkireelabs.com │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  zunkiree-search-api (Docker container)                       │   │
│  │  FastAPI + Uvicorn (port 8000)                                │   │
│  │                                                               │   │
│  │  /api/v1/widget/config/{site_id}  ─── Widget Config           │   │
│  │  /api/v1/query                    ─── Query + Verification    │   │
│  │  /api/v1/admin/*                  ─── Admin (ingestion, etc.) │   │
│  └──────┬──────────┬──────────┬──────────┬───────────────────────┘   │
└─────────┼──────────┼──────────┼──────────┼──────────────────────────┘
          │          │          │          │
          ▼          ▼          ▼          ▼
     Supabase    Pinecone    OpenAI     Gmail SMTP
    (Postgres)  (Vectors)   (LLM +     (Verification
                            Embeddings)  Emails)
```

---

## Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API Server** | FastAPI + Uvicorn | Async Python backend |
| **Container** | Docker + Docker Compose | Single-container deployment |
| **Reverse Proxy** | Traefik | SSL termination, routing via `api.zunkireelabs.com` |
| **Database** | Supabase (PostgreSQL) | Tenant data, chunks, configs, sessions, logs |
| **Vector Store** | Pinecone | Semantic search embeddings (namespace per tenant) |
| **LLM** | OpenAI GPT-4o-mini (default) / GPT-4o (premium) | Answer generation, reranking, classification |
| **Embeddings** | OpenAI text-embedding-3-large (3072 dims) | Query + document embeddings |
| **Email** | Gmail SMTP (Google Workspace) | Verification code delivery |
| **Widget CDN** | Vercel | Widget IIFE bundle hosting |

---

## Database Schema (Supabase PostgreSQL)

```
┌──────────────┐       ┌───────────────────┐       ┌──────────────────┐
│  customers   │       │  widget_configs    │       │    domains       │
├──────────────┤       ├───────────────────┤       ├──────────────────┤
│ id (PK)      │◄──┐   │ id (PK)           │       │ id (PK)          │
│ name         │   ├──►│ customer_id (FK)   │   ┌──►│ customer_id (FK) │
│ site_id (UQ) │   │   │ brand_name         │   │   │ domain           │
│ api_key      │   │   │ tone               │   │   │ is_active        │
│ is_active    │   │   │ primary_color      │   │   └──────────────────┘
│ created_at   │───┤   │ placeholder_text   │   │
└──────────────┘   │   │ welcome_message    │   │   ┌──────────────────────┐
                   │   │ fallback_message   │   │   │  ingestion_jobs      │
                   │   │ allowed_topics     │   │   ├──────────────────────┤
                   │   │ max_response_length│   │   │ id (PK)              │
                   │   │ show_sources       │   ├──►│ customer_id (FK)     │
                   │   │ show_suggestions   │   │   │ source_type          │
                   │   │ quick_actions      │   │   │ source_url           │
                   │   │ confidence_threshold│  │   │ source_filename      │
                   │   │ enable_identity_   │   │   │ status               │
                   │   │   verification     │   │   │ chunks_created       │
                   │   │ identity_custom_   │   │   │ error_message        │
                   │   │   fields           │   │   │ started_at           │
                   │   │ lead_intents       │   │   │ completed_at         │
                   │   └───────────────────┘   │   └──────────────────────┘
                   │                            │
                   │   ┌───────────────────┐   │   ┌──────────────────────┐
                   │   │  document_chunks   │   │   │  query_logs          │
                   │   ├───────────────────┤   │   ├──────────────────────┤
                   │   │ id (PK)           │   │   │ id (PK)              │
                   ├──►│ customer_id (FK)  │   ├──►│ customer_id (FK)     │
                   │   │ job_id (FK)       │   │   │ question             │
                   │   │ vector_id         │   │   │ answer               │
                   │   │ chunk_index       │   │   │ chunks_used          │
                   │   │ content           │   │   │ response_time_ms     │
                   │   │ content_preview   │   │   │ top_score            │
                   │   │ source_url        │   │   │ avg_score            │
                   │   │ source_title      │   │   │ fallback_triggered   │
                   │   │ token_count       │   │   │ retrieval_mode       │
                   │   │ search_vector     │   │   │ context_tokens       │
                   │   └───────────────────┘   │   │ rerank_triggered     │
                   │                            │   │ retrieval_empty      │
                   │   ┌────────────────────┐  │   │ llm_declined         │
                   │   │verification_sessions│  │   │ confidence_threshold │
                   │   ├────────────────────┤  │   └──────────────────────┘
                   │   │ id (PK)            │  │
                   ├──►│ customer_id (FK)   │  │   ┌──────────────────────┐
                   │   │ session_id (UQ)    │  │   │  user_profiles       │
                   │   │ state              │  │   ├──────────────────────┤
                   │   │ email              │  │   │ id (PK)              │
                   │   │ verification_code  │  ├──►│ customer_id (FK)     │
                   │   │ code_expires_at    │      │ email                │
                   │   │ code_attempts      │      │ name                 │
                   │   │ pending_question   │      │ custom_fields (JSON) │
                   │   │ user_name          │      │ user_type            │
                   │   │ pending_custom_    │      │ lead_intent          │
                   │   │   fields           │      └──────────────────────┘
                   │   │ current_field_index│
                   │   │ detected_intent    │
                   │   │ intent_signup_     │
                   │   │   fields           │
                   │   │ verified_at        │
                   │   └────────────────────┘
```

---

## Multi-Tenant Isolation

Every layer enforces tenant boundaries:

| Layer | Isolation Mechanism |
|-------|-------------------|
| **Pinecone** | Each tenant gets its own `namespace` (= `site_id`) |
| **PostgreSQL** | All tables filtered by `customer_id` (FK) |
| **Vector queries** | Defense-in-depth: namespace + metadata filter `site_id=$eq` |
| **Origin validation** | Widget requests checked against `domains` table |
| **Admin API** | Protected by `X-Admin-Key` header |

---

## API Endpoints

### Widget (Public)
| Method | Endpoint | Purpose |
|--------|---------|---------|
| `GET` | `/api/v1/widget/config/{site_id}` | Fetch branding, tone, suggestions |

### Query (Public)
| Method | Endpoint | Purpose |
|--------|---------|---------|
| `POST` | `/api/v1/query` | Submit question → get AI answer |

### Admin (Protected — `X-Admin-Key` header)
| Method | Endpoint | Purpose |
|--------|---------|---------|
| `POST` | `/api/v1/admin/customers` | Create tenant |
| `GET` | `/api/v1/admin/customers` | List tenants |
| `PUT` | `/api/v1/admin/config/{site_id}` | Update widget config |
| `POST` | `/api/v1/admin/ingest/url` | Ingest from URL (crawl) |
| `POST` | `/api/v1/admin/ingest/text` | Ingest raw text |
| `POST` | `/api/v1/admin/ingest/file` | Ingest PDF/DOCX/TXT |
| `POST` | `/api/v1/admin/ingest/qa` | Ingest single Q&A pair |
| `POST` | `/api/v1/admin/ingest/qa/batch` | Ingest batch Q&A pairs |
| `GET` | `/api/v1/admin/jobs/{site_id}` | List ingestion jobs |
| `GET` | `/api/v1/admin/stats/{site_id}` | Tenant ingestion stats |
| `GET` | `/api/v1/admin/retrieval-stats/{site_id}` | Retrieval health metrics |
| `POST` | `/api/v1/admin/reindex/{site_id}` | Delete all vectors (re-index) |

---

## Query Flow (The Main Pipeline)

This is the core of the system — what happens when a user sends a message.

```
User sends message
       │
       ▼
┌─────────────────────────────────────────────────┐
│  1. GREETING CHECK                               │
│  Is it "hi", "hello", etc.?                      │
│  YES → Return branded greeting + quick_actions   │
│  NO  → Continue                                  │
└──────────────────────┬──────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────┐
│  2. VERIFICATION STATE MACHINE                   │
│  (only if session_id provided AND                │
│   verification_enabled OR lead_intents exist)    │
│                                                  │
│  State: anonymous ──────────────────────────┐    │
│    │  Classify query (LLM):                 │    │
│    │  • "general" → skip to RAG             │    │
│    │  • "personal" + verification_enabled   │    │
│    │    → email_requested                   │    │
│    │  • "lead" → answer + CTA               │    │
│    │  • registration keywords → answer + CTA│    │
│    ▼                                        │    │
│  State: email_requested                     │    │
│    │  User submits email                    │    │
│    ▼                                        │    │
│  State: code_sent                           │    │
│    │  Send 6-digit code via Gmail SMTP      │    │
│    │  User submits code                     │    │
│    ▼                                        │    │
│  State: code_verified                       │    │
│    │  Returning user? → verified            │    │
│    │  New user? → name_requested            │    │
│    ▼                                        │    │
│  State: name_requested                      │    │
│    │  User submits name                     │    │
│    │  Custom fields configured? →           │    │
│    │    fields_requested                    │    │
│    │  No fields? → create profile, verified │    │
│    ▼                                        │    │
│  State: fields_requested                    │    │
│    │  Collect each field one by one         │    │
│    │  All done → create/update profile      │    │
│    ▼                                        │    │
│  State: verified                            │    │
│    │  Pass email + profile to RAG           │    │
│    │  for personalized answers              │    │
│    ▼                                        │    │
└──────────────────────┬──────────────────────┘    │
                       │◄─────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────┐
│  3. RAG PIPELINE                                 │
│                                                  │
│  a) EMBED: question → OpenAI text-embedding-     │
│     3-large (3072 dims)                          │
│                                                  │
│  b) VECTOR SEARCH: Pinecone query                │
│     (namespace=site_id, top_k=8)                 │
│                                                  │
│  c) KEYWORD SEARCH: PostgreSQL full-text          │
│     ts_rank on document_chunks.search_vector     │
│     (boosted with user_email if verified)        │
│                                                  │
│  d) FUSION: Reciprocal Rank Fusion (k=60)        │
│     Merges vector + keyword results              │
│                                                  │
│  e) ADAPTIVE TOP-K:                              │
│     top_score > 0.6  → top_k=3 (high confidence)│
│     top_score >= 0.4 → top_k=5 (medium)         │
│     top_score < 0.4  → top_k=8 (low, cast wide) │
│                                                  │
│  f) LLM RERANKING (optional):                    │
│     Triggers when 0.25 < top_score < 0.45        │
│     LLM ranks passages by relevance              │
│                                                  │
│  g) FETCH CHUNKS: PostgreSQL by vector_id        │
│     (defense-in-depth: filtered by customer_id)  │
│                                                  │
│  h) TOKEN CAP: max 4000 context tokens           │
│                                                  │
│  i) LLM ANSWER: GPT-4o-mini generates response   │
│     with brand tone, fallback message,           │
│     and user profile (if verified)               │
│                                                  │
│  j) SUGGESTIONS: GPT generates 2 follow-ups      │
│                                                  │
│  k) SOURCES: Deduplicated source URLs from chunks│
└──────────────────────┬──────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────┐
│  4. LOGGING & METRICS                            │
│                                                  │
│  Logged to query_logs:                           │
│  • top_score, avg_score, context_tokens          │
│  • retrieval_mode (hybrid / hybrid_rerank)       │
│  • fallback_triggered, retrieval_empty           │
│  • llm_declined, rerank_triggered                │
│  • response_time_ms                              │
│                                                  │
│  Health Score formula (0-100):                   │
│    + score_component (30pts)                     │
│    + context_component (10pts)                   │
│    + threshold_component (20pts)                 │
│    - llm_penalty (25pts)                         │
│    - empty_penalty (40pts)                       │
└──────────────────────┬──────────────────────────┘
                       ▼
              Return to widget:
              { answer, suggestions, sources }
```

---

## Ingestion Flow

How data gets into the system for a tenant:

```
Admin API call (with X-Admin-Key)
       │
       ▼
┌──────────────────────────────────┐
│  Source Types:                    │
│  • URL (crawl with depth 0-2)    │
│  • Text (raw paste)              │
│  • File (PDF, DOCX, TXT ≤10MB)  │
│  • Q&A seed pair                 │
│  • Q&A batch (up to 50 pairs)    │
└──────────┬───────────────────────┘
           ▼
┌──────────────────────────────────┐
│  1. Extract text                  │
│     URL → crawl + BeautifulSoup  │
│     PDF → PyPDF / pdfplumber     │
│     DOCX → python-docx           │
│     Text → direct                │
│     Q&A → "Q: ...\nA: ..."      │
└──────────┬───────────────────────┘
           ▼
┌──────────────────────────────────┐
│  2. Chunk text                    │
│     Semantic chunking with        │
│     token-based splitting         │
│     Min content: 300 chars        │
└──────────┬───────────────────────┘
           ▼
┌──────────────────────────────────┐
│  3. Generate embeddings           │
│     OpenAI text-embedding-3-large │
│     3072 dimensions               │
│     Batch size: 100               │
└──────────┬───────────────────────┘
           ▼
┌──────────────────────────────────┐
│  4. Store (dual write)            │
│                                   │
│  Pinecone:                        │
│    vector_id, embedding, metadata │
│    namespace = site_id            │
│                                   │
│  PostgreSQL (document_chunks):    │
│    full content, source_url,      │
│    source_title, token_count,     │
│    search_vector (tsvector)       │
└──────────────────────────────────┘
```

---

## Query Classification (Personalization Layer)

Determines whether a query needs identity verification:

```
User question
     │
     ▼
┌────────────────────────────────────────────┐
│ 1. Registration keyword check              │
│    ("register", "sign up", "enroll", etc.) │
│    Match? → type: "personal"               │
│    (but handled as lead CTA, not gated)    │
└──────────┬─────────────────────────────────┘
           │ no match
           ▼
┌────────────────────────────────────────────┐
│ 2. Lead intent keyword pre-screen          │
│    Check against tenant's lead_intents     │
│    config keywords                         │
│    Match? → LLM confirms intent            │
│    Confirmed? → type: "lead"               │
│    (answer via RAG + append signup CTA)    │
└──────────┬─────────────────────────────────┘
           │ no match
           ▼
┌────────────────────────────────────────────┐
│ 3. LLM classification (GPT-4o-mini)       │
│    "personal" = REQUIRES user identity     │
│      (e.g., "show my grades")             │
│    "general" = answerable without identity │
│      (e.g., "I want to study abroad")     │
└────────────────────────────────────────────┘
```

---

## Widget Architecture (Frontend)

```
<script src="zunkiree-widget.iife.js"
        data-site-id="admizz"
        data-api-url="https://api.zunkireelabs.com">

main.tsx
  │  Reads data-site-id, data-api-url from script tag
  │  Creates shadow-DOM-style container
  ▼
Widget.tsx (orchestrator)
  │  State: isOpen, messages[], config, sessionId
  │  API calls: GET /widget/config, POST /query
  │
  ├── CollapsedBar.tsx
  │     Card gradient (#2067fb → #000b22)
  │     Animated conic-gradient border on input
  │     AI sparkles icon, suggestion chips
  │     Send button (#eb1600)
  │
  └── ExpandedPanel.tsx
        Pastel gradient background
        Header with brand name + close
        Hero: "How can {brand} help?" + chips
        Conversation bubbles (user/assistant)
        Sticky input with animated border
        Backdrop blur (click to close)

styles.ts
  │  CSS-in-JS template string
  │  All classes prefixed zk-
  │  !important on inputs to prevent host CSS bleed
  │  Responsive: desktop (720px+), tablet, mobile
```

---

## Configuration (Per-Tenant via widget_configs)

| Setting | Default | Purpose |
|---------|---------|---------|
| `brand_name` | customer name | Display name in widget header |
| `tone` | neutral | LLM response tone (formal/neutral/friendly) |
| `primary_color` | #2563eb | Widget accent color |
| `placeholder_text` | "Ask a question..." | Input placeholder |
| `fallback_message` | "I don't have that..." | When LLM can't answer |
| `quick_actions` | [] | Suggestion chips (JSON array) |
| `confidence_threshold` | 0.25 | Min Pinecone score to trust results |
| `show_sources` | true | Show source links in responses |
| `show_suggestions` | true | Show follow-up suggestions |
| `enable_identity_verification` | false | Gate personal queries behind email verification |
| `identity_custom_fields` | null | Custom signup fields (JSON) |
| `lead_intents` | null | Lead capture intent configs (JSON) |

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | OpenAI embeddings + LLM |
| `PINECONE_API_KEY` | Yes | Vector store |
| `PINECONE_HOST` | Yes | Pinecone index endpoint |
| `DATABASE_URL` | Yes | Supabase PostgreSQL connection |
| `API_SECRET_KEY` | Yes | Admin API authentication |
| `ALLOWED_ORIGINS` | No | CORS origins (default: localhost) |
| `LLM_MODEL` | No | Default LLM (default: gpt-4o-mini) |
| `LLM_MODEL_PREMIUM` | No | Premium LLM (default: gpt-4o) |
| `SMTP_HOST` | No | Email server (default: smtp.gmail.com) |
| `SMTP_PORT` | No | SMTP port (default: 465) |
| `SMTP_USERNAME` | No | SMTP login email |
| `SMTP_PASSWORD` | No | SMTP app password |
| `SMTP_FROM_EMAIL` | No | Sender address |

---

## File Structure

```
backend/
├── app/
│   ├── main.py                    # FastAPI app, lifespan, CORS, routers
│   ├── config.py                  # Pydantic settings from .env
│   ├── database.py                # SQLAlchemy async engine + session
│   ├── api/
│   │   ├── query.py               # POST /query — main query + verification flow
│   │   ├── widget.py              # GET /widget/config — widget initialization
│   │   └── admin.py               # All admin endpoints (CRUD, ingestion, stats)
│   ├── models/
│   │   ├── customer.py            # Customer tenant model
│   │   ├── domain.py              # Allowed origin domains
│   │   ├── widget_config.py       # Per-tenant widget configuration
│   │   ├── ingestion.py           # IngestionJob + DocumentChunk
│   │   ├── query_log.py           # Query analytics logging
│   │   ├── verification.py        # VerificationSession state machine
│   │   └── user_profile.py        # Verified user profiles
│   ├── services/
│   │   ├── query.py               # RAG pipeline (embed → search → fuse → answer)
│   │   ├── llm.py                 # LLM abstraction (OpenAI provider, prompts)
│   │   ├── embeddings.py          # OpenAI embedding service
│   │   ├── vector_store.py        # Pinecone upsert/query/delete
│   │   ├── ingestion.py           # Content ingestion (URL, text, file, Q&A)
│   │   ├── verification.py        # Email verification state machine
│   │   ├── personalization.py     # Query classifier (general/personal/lead)
│   │   └── email.py               # SMTP email sending
│   └── utils/
│       ├── chunking.py            # Text chunking + token counting
│       ├── crawling.py            # URL crawler
│       └── file_parsers.py        # PDF, DOCX, TXT extractors
├── Dockerfile
├── requirements.txt
└── .env

widget/
├── src/
│   ├── main.tsx                   # Entry point, script tag parsing
│   ├── components/
│   │   ├── Widget.tsx             # Orchestrator, state, API calls
│   │   ├── CollapsedBar.tsx       # Collapsed card view
│   │   ├── ExpandedPanel.tsx      # Full conversation panel
│   │   └── styles.ts             # All CSS-in-JS styles
│   └── styles/
│       └── tokens.ts             # Design tokens (v2)
├── package.json
└── vite.config.ts

docker-compose.yml                 # Single service, Traefik labels
```
