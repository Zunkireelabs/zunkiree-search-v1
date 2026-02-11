# Zunkiree Search v1 - Session Log

> Last Updated: January 7, 2025
> Status: **PHASE 1 EXECUTION** - OpenAI credits added, ingesting content

---

## Phase 1 — Product Validation

### Task 1: Ingest ZunkireeLabs Content
- Status: **DONE**
- Date: January 7, 2025
- Result: 6 chunks indexed from zunkireelabs.com (homepage, services, contact)
- Exit condition: ✅ Core pages ingested, chunks indexed in Pinecone

### Task 2: End-to-End Query Validation
- Status: **DONE**
- Date: January 7, 2025
- Result: Query "What services do you offer?" returns accurate, grounded answer
- Exit condition: ✅ Real queries return grounded answers

### Task 3: Answer Quality Tightening
- Status: **DONE**
- Date: January 7, 2025
- Result: Tested "capital of France" - correctly returned fallback (no hallucination)
- Exit condition: ✅ Prompt enforces context-only answers, fallback works

### Task 4: Lock v1 Behavior
- Status: **DONE**
- Date: January 7, 2025
- Result: Verified - single-turn Q&A, no user identity, no memory, no analytics UI
- Exit condition: ✅ v1 behavior locked

### Task 5: Floating UI v1
- Status: Pending
- Exit condition: ChatGPT-style floating bottom bar inside widget

### Task 6: Pilot #2 Onboarding
- Status: Pending
- Exit condition: One external pilot (Admizz or Khems) live

---

## December 28, 2024 - Widget Embedded on ZunkireeLabs Website

### Milestone
Widget successfully embedded and validated on dev-web.zunkireelabs.com

### What Was Done
1. ✅ Cleaned up debug logging from backend (removed temporary troubleshooting code)
2. ✅ Generated embed prompt for ZunkireeLabs website (VPS)
3. ✅ Widget embedded on dev-web.zunkireelabs.com
4. ✅ Visual validation passed:
   - Widget script loads without errors
   - Floating search button appears
   - Search modal opens on click
   - UI renders correctly with ZunkireeLabs branding
5. ✅ Created `docs/TODO.md` for project tracking:
   - Blocked items (OpenAI credits)
   - Next steps after blocker resolved
   - Pilot customer roadmap
   - Future enhancements backlog
   - Technical debt items
   - Quick reference (URLs, credentials, embed code)

### Current State
- **Widget**: Live and functional (UI only)
- **AI Responses**: Not working (expected - OpenAI credits not added yet)
- **Phase**: Visual/frontend validation complete

### Next Steps (When Ready)
1. Add OpenAI credits ($5-10) at https://platform.openai.com/settings/organization/billing/overview
2. Ingest ZunkireeLabs content via admin panel
3. Test end-to-end query flow
4. Go live with full functionality

---

## December 27, 2024 - ZunkireeLabs Customer Created

### Production URLs
| Service | URL |
|---------|-----|
| **Backend API** | https://zunkiree-search-v1-production.up.railway.app |
| **Widget CDN** | https://zunkiree-search-v1.vercel.app |
| **Admin Panel** | https://zunkiree-admin.vercel.app |
| **API Docs** | https://zunkiree-search-v1-production.up.railway.app/docs |
| **Widget JS** | https://zunkiree-search-v1.vercel.app/zunkiree-widget.iife.js |

### Deployment Stack
- **Backend**: Railway (FastAPI)
- **Widget**: Vercel (CDN with CORS headers)
- **Admin Panel**: Vercel (separate project)
- **Database**: Supabase (PostgreSQL via Supavisor pooler)
- **Vector Store**: Pinecone
- **LLM**: OpenAI (gpt-4o-mini) - NEEDS CREDITS

### ZunkireeLabs Customer (Created)
| Field | Value |
|-------|-------|
| **Customer ID** | `063be854-4061-4b2c-b730-3a27e3a4afe7` |
| **Site ID** | `zunkireelabs` |
| **API Key** | `zk_live_zunkireelabs_kFgdkzGSASr_8-olH3Y0SnsWU9GnAV_b` |
| **Allowed Domains** | dev-web.zunkireelabs.com, zunkireelabs.com, www.zunkireelabs.com, localhost |

### Widget Embed Code for ZunkireeLabs
```html
<script
  src="https://zunkiree-search-v1.vercel.app/zunkiree-widget.iife.js"
  data-site-id="zunkireelabs"
  data-api-url="https://zunkiree-search-v1-production.up.railway.app"
></script>
```

### Progress
1. ✅ Production deployment complete
2. ✅ Admin panel deployed to Vercel
3. ✅ Database connection fixed (switched to Supabase pooler for IPv4 compatibility)
4. ✅ Created "zunkireelabs" customer via API
5. ✅ Widget embedded on dev-web.zunkireelabs.com (visual validation passed)
6. ⏳ Add OpenAI credits ($5-10) - **CURRENT BLOCKER**
7. ⏳ Ingest ZunkireeLabs content
8. ⏳ Test end-to-end

### Issues Fixed Today
- **Admin key validation**: Railway env var had malformed value, fixed by re-adding
- **Database connection**: Supabase direct connection not IPv4 compatible, switched to Supavisor pooler (`aws-1-ap-south-1.pooler.supabase.com:6543`)

---

## December 26, 2024 - LLM Abstraction Layer

### Changes Made

1. **Changed default model** from `gpt-4o` to `gpt-4o-mini` (cheaper, faster)
2. **Implemented LLM abstraction layer** in `backend/app/services/llm.py`:
   - `BaseLLMProvider` - Abstract interface for LLM providers
   - `OpenAIProvider` - OpenAI implementation
   - `LLMService` - Business logic layer using composition
   - `get_llm_service(model_tier)` - Factory function with caching
3. **Added model tier support** (default/premium) for future routing
4. **Updated configuration** in `backend/app/config.py` with new LLM settings
5. **Created documentation** at `docs/llm-abstraction.md`

### Files Modified
- `backend/app/services/llm.py` - Refactored with abstraction layer
- `backend/app/config.py` - Added LLM configuration settings
- `backend/.env` - Added `LLM_MODEL=gpt-4o-mini` and `LLM_MODEL_PREMIUM=gpt-4o`
- `docs/llm-abstraction.md` - New documentation file
- `zunkiree-search-v1.md` - Updated tech stack section
- `docs/architecture.md` - Updated LLM references
- `docs/implementation-plan.md` - Updated infrastructure choices
- `docs/api-spec.md` - Added LLM configuration section

### Design Principles
- **No hardcoding**: Model configurable via environment variables
- **Abstraction**: Easy to add future providers (Anthropic, Azure, etc.)
- **Cost optimization**: gpt-4o-mini is ~20x cheaper than gpt-4o
- **Accuracy from RAG**: Not from expensive models

### Project Roadmap Created
- Created `docs/project-roadmap.md` for tracking all tasks
- Phase-wise organization with status indicators
- Blockers and dependencies documented
- Future enhancements backlog

---

## Quick Summary

Zunkiree Search v1 is an AI-powered embeddable search widget. We built:
- FastAPI backend with RAG (Retrieval-Augmented Generation)
- React widget (embeddable via single script tag)
- Admin panel for managing customers and data ingestion
- Full documentation

**Only blocker:** OpenAI API needs credits ($5-10) for embeddings and answer generation.

---

## Project Structure

```
zunkiree-search-v1/
├── backend/                 # FastAPI Python backend
│   ├── app/
│   │   ├── main.py         # FastAPI application entry
│   │   ├── config.py       # Settings/environment config
│   │   ├── database.py     # PostgreSQL connection
│   │   ├── models/         # SQLAlchemy models
│   │   │   ├── customer.py
│   │   │   ├── domain.py
│   │   │   ├── widget_config.py
│   │   │   ├── ingestion.py
│   │   │   └── query_log.py
│   │   ├── services/       # Business logic
│   │   │   ├── embeddings.py    # OpenAI embeddings
│   │   │   ├── vector_store.py  # Pinecone operations
│   │   │   ├── llm.py           # LLM abstraction layer (gpt-4o-mini default)
│   │   │   ├── query.py         # Query processing
│   │   │   └── ingestion.py     # Data ingestion
│   │   ├── api/            # API endpoints
│   │   │   ├── query.py    # POST /api/v1/query
│   │   │   ├── widget.py   # GET /api/v1/widget/config
│   │   │   └── admin.py    # Admin endpoints
│   │   └── utils/          # Utilities
│   │       ├── chunking.py # Text chunking
│   │       └── crawling.py # URL crawling, PDF extraction
│   ├── venv/               # Python virtual environment
│   ├── requirements.txt    # Python dependencies
│   ├── .env                # Environment variables (has credentials)
│   └── .env.example        # Template for env vars
├── widget/                  # React widget
│   ├── src/
│   │   ├── main.tsx        # Widget entry point
│   │   └── components/
│   │       ├── Widget.tsx  # Main widget component
│   │       └── styles.ts   # CSS-in-JS styles
│   ├── dist/               # Production build
│   │   ├── zunkiree-widget.iife.js  # Embeddable bundle (149KB)
│   │   └── demo.html       # Demo page
│   ├── package.json
│   ├── vite.config.ts
│   └── index.html          # Dev server page
├── admin/                   # Admin UI
│   └── index.html          # Single-page admin panel
├── docs/                    # Documentation
│   ├── implementation-plan.md
│   ├── architecture.md
│   ├── api-spec.md
│   ├── database-schema.md
│   ├── widget-spec.md
│   └── llm-abstraction.md   # LLM strategy & abstraction layer
├── session-log/            # This log
│   └── session-log.md
└── zunkiree-search-v1.md   # Original specification
```

---

## Infrastructure Credentials

### Pinecone (Vector Database)
```
PINECONE_API_KEY=pcsk_3gJP6a_4zricZw7kWKLY8eP1u5ShPwM4NXBNxqSUTqxRcAf4raCBCBBYRSJag8suQKteSf
PINECONE_HOST=https://zunkiree-search-vuzid6w.svc.aped-4627-b74a.pinecone.io
PINECONE_INDEX_NAME=zunkiree-search
```
- Index: `zunkiree-search`
- Dimensions: 3072 (for text-embedding-3-large)
- Metric: cosine
- Region: AWS us-east-1
- Status: **Ready**

### Supabase (PostgreSQL)
```
DATABASE_URL=postgresql+asyncpg://postgres:r4HuWLWPegFBjTq4t803@db.qzgcowcrtggmttfczbdo.supabase.co:5432/postgres
```
- Project: zunkiree-search
- Region: Asia-Pacific
- Status: **Ready**

### OpenAI
```
OPENAI_API_KEY=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
```
- Status: **NEEDS CREDITS** - Add $5-10 at https://platform.openai.com/settings/organization/billing/overview

### App Settings
```
API_SECRET_KEY=zk_admin_secret_change_this_in_production
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

---

## How to Start the Servers

### 1. Backend API (Port 8000)
```bash
cd C:\Users\sadin\Desktop\Zunkireelabs\dev-folder\zunkiree-search-v1\backend
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

### 2. Widget Dev Server (Port 5173)
```bash
cd C:\Users\sadin\Desktop\Zunkireelabs\dev-folder\zunkiree-search-v1\widget
npm run dev
```
- Demo: http://localhost:5173

### 3. Admin Panel (Port 3000)
```bash
cd C:\Users\sadin\Desktop\Zunkireelabs\dev-folder\zunkiree-search-v1\admin
py -m http.server 3000
```
- Admin: http://localhost:3000

---

## API Endpoints

### Public (Widget)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/query` | Submit question, get AI answer |
| GET | `/api/v1/widget/config/{site_id}` | Get widget configuration |

### Admin (requires X-Admin-Key header)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/admin/customers` | Create new customer |
| POST | `/api/v1/admin/ingest/url` | Ingest from URL |
| POST | `/api/v1/admin/ingest/text` | Ingest raw text |
| POST | `/api/v1/admin/ingest/document` | Upload PDF |
| PUT | `/api/v1/admin/config/{customer_id}` | Update widget config |
| GET | `/api/v1/admin/jobs/{customer_id}` | List ingestion jobs |
| POST | `/api/v1/admin/reindex/{customer_id}` | Delete all vectors |

---

## Database Tables

1. **customers** - Customer/tenant records
2. **domains** - Allowed domains per customer
3. **widget_configs** - Widget appearance/behavior settings
4. **ingestion_jobs** - Data ingestion job tracking
5. **document_chunks** - Metadata for indexed chunks
6. **query_logs** - Query history for debugging

Tables are auto-created on first backend startup.

---

## What's Complete

| Component | Status | Notes |
|-----------|--------|-------|
| Project structure | ✅ Done | |
| FastAPI backend | ✅ Done | |
| Database models | ✅ Done | Auto-creates tables |
| Pinecone integration | ✅ Done | |
| OpenAI integration | ✅ Done | Needs credits |
| Ingestion service | ✅ Done | URL, text, PDF |
| Query service | ✅ Done | RAG pipeline |
| Admin API | ✅ Done | All endpoints |
| React widget | ✅ Done | |
| Widget bundle | ✅ Done | 149KB IIFE |
| Admin UI | ✅ Done | Single HTML file |
| Documentation | ✅ Done | 5 docs in /docs |

---

## What's Pending

| Task | Status | Blocker |
|------|--------|---------|
| Add OpenAI credits | ⏳ Pending | Need $5-10 |
| Ingest ZunkireeLabs content | ⏳ Pending | OpenAI credits |
| Test end-to-end query flow | ⏳ Pending | OpenAI credits |
| Setup pilot customers | ⏳ Pending | OpenAI credits |

**Note:** Production deployment is COMPLETE. Widget is live on dev-web.zunkireelabs.com (visual validation passed).

---

## Issues Encountered & Solutions

### 1. Python not installed
- **Issue:** `python` command not found
- **Solution:** Installed Python 3.14.2 via python.org, added to PATH

### 2. Pinecone package renamed
- **Issue:** `pinecone-client` package deprecated
- **Solution:** Changed to `pinecone>=8.0.0` in requirements.txt

### 3. Python 3.14 compatibility
- **Issue:** Some packages didn't support Python 3.14
- **Solution:** Used flexible version requirements (>=) instead of pinned versions

### 4. OpenAI quota exceeded
- **Issue:** API returns 429 error "insufficient_quota"
- **Solution:** Need to add billing/credits to OpenAI account

---

## Customers Created

### ZunkireeLabs (Production)
```
Site ID: zunkireelabs
API Key: zk_live_zunkireelabs_kFgdkzGSASr_8-olH3Y0SnsWU9GnAV_b
Allowed Domains: dev-web.zunkireelabs.com, zunkireelabs.com, www.zunkireelabs.com, localhost
```

### Test Customer (Development)
```
Site ID: test
API Key: zk_live_test_L9dcIYzWTZxwoU-zKk6RMwTbf526hAPR
Allowed Domains: localhost, 127.0.0.1
```

---

## Widget Embed Code

```html
<script
  src="https://cdn.zunkiree.ai/widget/zunkiree-widget.iife.js"
  data-site-id="YOUR_SITE_ID"
  data-api-url="https://api.zunkiree.ai"
></script>
```

For local development:
```html
<script
  src="./zunkiree-widget.iife.js"
  data-site-id="test"
  data-api-url="http://localhost:8000"
></script>
```

---

## Pilot Customers (To Setup)

| Customer | Site ID | Tone | Data Source |
|----------|---------|------|-------------|
| Admizz Education | admizz | Professional | Country pages, FAQs |
| Khems Cleaning | khems | Friendly | Services, pricing |
| Guntabya (OTA) | guntabya | Neutral | Listings, policies |

---

## Next Steps

1. **Add OpenAI credits** ($5-10)
   - Go to: https://platform.openai.com/settings/organization/billing/overview

2. **Test ingestion**
   - Start backend
   - Open admin panel
   - Ingest sample text for "test" customer

3. **Test query**
   - Open widget demo
   - Ask a question
   - Verify answer comes from ingested data

4. **Setup pilot customers**
   - Create customers via admin panel
   - Ingest their data
   - Generate embed codes

5. **Deploy to production**
   - Backend: Railway or Fly.io
   - Widget: Vercel or Cloudflare Pages
   - Update CORS origins

---

## File Locations Quick Reference

| File | Path |
|------|------|
| **Project Roadmap** | `docs/project-roadmap.md` |
| Backend entry | `backend/app/main.py` |
| Environment vars | `backend/.env` |
| LLM service | `backend/app/services/llm.py` |
| LLM docs | `docs/llm-abstraction.md` |
| Widget source | `widget/src/components/Widget.tsx` |
| Widget bundle | `widget/dist/zunkiree-widget.iife.js` |
| Admin panel | `admin/index.html` |
| Original spec | `zunkiree-search-v1.md` |
| This log | `session-log/session-log.md` |

---

## Commands Cheat Sheet

```bash
# Start everything (run in separate terminals)
cd backend && venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd widget && npm run dev
cd admin && py -m http.server 3000

# Rebuild widget
cd widget && npm run build

# Install new Python package
cd backend && venv\Scripts\pip install <package>

# Install new Node package
cd widget && npm install <package>
```

---

## Contact/Notes

- Company: ZunkireeLabs
- Product: Zunkiree Search (Module of Zunkiree AI Platform)
- Stage: v1 / Pilot / Early Access
- Built with: Claude Code

---

*This log should be updated whenever significant progress is made.*
