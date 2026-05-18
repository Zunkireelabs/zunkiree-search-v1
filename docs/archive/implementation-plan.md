# Zunkiree Search v1 - Implementation Plan

## Overview
Build an AI-powered embeddable search widget for 3 pilot customers.

## Confirmed Infrastructure Choices
| Component | Choice |
|-----------|--------|
| PostgreSQL | **Supabase** |
| Object Storage | **Cloudflare R2** |
| Vector DB | **Pinecone** |
| LLM | **OpenAI gpt-4o-mini (default) / gpt-4o (premium)** - See [LLM Abstraction](llm-abstraction.md) |
| Embeddings | **text-embedding-3-large** |

---

## Phase 1: Project Foundation & Core Backend

### 1.1 Project Setup
- Initialize Python project with pip
- Setup FastAPI application structure
- Configure environment variables template
- Setup PostgreSQL database connection
- Setup Pinecone client
- Setup OpenAI client

### 1.2 Database Schema (PostgreSQL)
- `customers` table (id, name, api_key, created_at)
- `domains` table (id, customer_id, domain, allowed)
- `widget_configs` table (id, customer_id, brand_name, tone, primary_color, allowed_topics)
- `ingestion_jobs` table (id, customer_id, source_type, source_url, status, created_at)
- `document_chunks` table (id, customer_id, source_id, chunk_index, content_preview, vector_id)

### 1.3 Ingestion Service
- URL crawler (BeautifulSoup/httpx)
- PDF text extraction (pdfplumber)
- Text chunking (~500 tokens per chunk, 50 token overlap)
- Embedding generation (text-embedding-3-large)
- Pinecone upsert with customer namespace

### 1.4 Query Service
- Receive query + site_id
- Validate domain allowlist
- Generate query embedding
- Retrieve top-k chunks from Pinecone
- Build grounded prompt with context
- Call LLM via abstraction layer (gpt-4o-mini default)
- Validate response
- Return response with optional follow-ups

### 1.5 Admin Service (Internal API)
- Upload documents endpoint
- Trigger re-index endpoint
- Update config endpoint
- List ingestion jobs endpoint

---

## Phase 2: Frontend Widget

### 2.1 Widget Development
- React + Vite setup
- Minimal UI components:
  - Floating trigger button
  - Chat container
  - Message bubbles (user/assistant)
  - Input field
  - Loading indicator
- No emojis, no personality
- Keyboard accessible

### 2.2 Build & Embed
- Vite build to single JS bundle
- IIFE wrapper for embedding
- Read `data-site-id` from script tag
- CSS-in-JS (no external stylesheets)
- Configurable colors via API response

---

## Phase 3: Admin Interface (Internal Only)

### 3.1 Simple Admin UI
- Basic React app (separate from widget)
- Protected by API key
- Features:
  - Upload documents (drag/drop)
  - Trigger URL crawl
  - Edit widget config (brand, tone, colors)
  - View ingestion status

---

## Phase 4: Pilot Integration & Testing

### 4.1 Per-Customer Setup
- Create customer records
- Configure domains
- Ingest initial data
- Generate embed code

### 4.2 Testing
- Test queries for each pilot
- Edge case handling
- Fallback responses
- Performance testing

---

## File Structure

```
zunkiree-search-v1/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   ├── services/
│   │   ├── api/
│   │   └── utils/
│   ├── requirements.txt
│   └── .env.example
├── widget/
│   ├── src/
│   ├── vite.config.ts
│   └── package.json
├── admin/
│   ├── src/
│   └── package.json
└── docs/
```

---

## Key Technical Decisions

1. **Pinecone Namespaces**: Each customer gets a namespace (e.g., `admizz`, `khems`, `guntabya`)
2. **Chunking Strategy**: ~500 tokens, overlap 50 tokens, semantic boundaries
3. **Retrieval**: Top 5 chunks
4. **Prompt Structure**: System prompt + context chunks + user question
5. **Rate Limiting**: Cloudflare (not application-level for v1)

---

## Deliverables

1. `/backend` - FastAPI application
2. `/widget` - Embeddable React widget
3. `/admin` - Simple admin interface
4. `/docs` - Documentation files
