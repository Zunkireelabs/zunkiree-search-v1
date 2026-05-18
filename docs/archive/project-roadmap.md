# Zunkiree Search v1 - Project Roadmap

> Last Updated: December 26, 2024
> Overall Status: **95% Code Complete** | **Testing Blocked**

---

## Status Overview

| Phase | Description | Done | Pending | Blocked | Status |
|-------|-------------|------|---------|---------|--------|
| 1 | Core Backend | 12 | 0 | 2 | 🟡 Blocked |
| 2 | Widget v1 (Chat) | 8 | 0 | 0 | 🟢 Complete |
| 2.1 | Widget v2 (Search) | 1 | 5 | 0 | 🔵 In Progress |
| 3 | Admin Panel v1 | 5 | 0 | 0 | 🟢 Complete |
| 3.1 | Admin Panel v2 | 0 | 4 | 0 | ⬜ Future |
| 4 | Pilot Integration | 1 | 0 | 3 | 🟡 Blocked |
| 5 | Production Deploy | 0 | 5 | 0 | ⬜ Not Started |

**Legend:** 🟢 Complete | 🟡 Blocked | 🔵 In Progress | ⬜ Not Started

---

## Phase 1: Core Backend

### Completed

- [x] **Project Setup**
  - FastAPI application structure
  - Python virtual environment
  - Requirements.txt with dependencies
  - Environment variables template (.env.example)

- [x] **Database (Supabase PostgreSQL)**
  - Connection setup with asyncpg
  - SQLAlchemy models created
  - Auto-migration on startup
  - Tables: customers, domains, widget_configs, ingestion_jobs, document_chunks, query_logs

- [x] **Vector Database (Pinecone)**
  - Pinecone client setup
  - Index created: `zunkiree-search`
  - Namespace-per-customer isolation
  - 3072 dimensions (text-embedding-3-large)

- [x] **OpenAI Integration**
  - Embeddings service (text-embedding-3-large)
  - LLM abstraction layer implemented
  - Default model: gpt-4o-mini
  - Premium model: gpt-4o (ready for future use)

- [x] **Ingestion Service**
  - URL crawling (httpx + BeautifulSoup)
  - PDF extraction (pdfplumber)
  - Raw text ingestion
  - Text chunking (~500 tokens, 50 overlap)

- [x] **Query Service**
  - RAG pipeline complete
  - Domain validation
  - Context retrieval from Pinecone
  - Grounded prompt generation
  - Response validation

- [x] **Admin API**
  - POST /api/v1/admin/customers
  - POST /api/v1/admin/ingest/url
  - POST /api/v1/admin/ingest/text
  - POST /api/v1/admin/ingest/document
  - PUT /api/v1/admin/config/{customer_id}
  - GET /api/v1/admin/jobs/{customer_id}
  - POST /api/v1/admin/reindex/{customer_id}

### Blocked

- [ ] **Test embeddings generation**
  - Status: ⏸️ BLOCKED
  - Blocker: OpenAI API credits needed ($5-10)
  - Action: Add credits at https://platform.openai.com/settings/organization/billing/overview

- [ ] **Test query flow end-to-end**
  - Status: ⏸️ BLOCKED
  - Blocker: OpenAI API credits needed
  - Depends on: Embeddings working

---

## Phase 2: Widget v1 (Chat Style)

### Completed

- [x] **Project Setup**
  - React + Vite configuration
  - TypeScript setup
  - CSS-in-JS styling

- [x] **UI Components**
  - Floating trigger button
  - Chat window container
  - Message bubbles (user/assistant)
  - Input field with send button
  - Loading indicator
  - Follow-up suggestions

- [x] **Build & Distribution**
  - IIFE bundle created (149KB)
  - Single script tag embed
  - data-site-id configuration
  - data-api-url configuration

- [x] **Demo Page**
  - Local demo at widget/dist/demo.html
  - Dev server at http://localhost:5173

### Files
```
widget/
├── src/
│   ├── main.tsx
│   └── components/
│       ├── Widget.tsx
│       └── styles.ts
├── dist/
│   ├── zunkiree-widget.iife.js
│   └── demo.html
├── package.json
└── vite.config.ts
```

---

## Phase 2.1: Widget v2 (Search-First Redesign)

> **Goal:** Transform from chatbot-style to search-first experience

### Completed

- [x] **Style Guide Created**
  - `docs/widget-style-guide.md`
  - Design tokens defined
  - Component specifications
  - 3 embed modes designed (Hero, Inline, Floating)
  - Accessibility guidelines

### In Progress

- [ ] **Component Refactor**
  - [ ] ZunkireeSearch.tsx (main component)
  - [ ] SearchBar.tsx (search input)
  - [ ] ResultsPanel.tsx (results display)
  - [ ] QuickActions.tsx (suggestion chips)
  - [ ] LoadingState.tsx (skeleton loader)

- [ ] **Styles Refactor**
  - [ ] tokens.ts (design tokens)
  - [ ] Component-specific styles
  - [ ] Responsive design
  - [ ] Animation system

### Pending

- [ ] **New Embed Modes**
  - Hero mode (full-width, prominent)
  - Inline mode (embedded in content)
  - Floating mode (legacy support)

- [ ] **Testing & Polish**
  - Cross-browser testing
  - Mobile responsiveness
  - Accessibility audit
  - Bundle size optimization

### Design Reference
See: [Widget Style Guide](widget-style-guide.md)

---

## Phase 3: Admin Panel

### Completed

- [x] **Single-page Admin UI**
  - Pure HTML/CSS/JS (no framework)
  - API key authentication
  - Clean, functional design

- [x] **Customer Management**
  - Create new customers
  - View customer list

- [x] **Data Ingestion**
  - URL ingestion form
  - Text ingestion form
  - PDF upload (planned)

- [x] **Configuration**
  - Update widget settings
  - Brand name, tone, colors

- [x] **Job Monitoring**
  - View ingestion job status

### Files
```
admin/
└── index.html
```

---

## Phase 3.1: Admin Panel Redesign (Future)

> **Goal:** Create style guide and modernize admin panel UI
> **Status:** ⬜ Not Started (will do after widget v2)

### Planned

- [ ] **Admin Style Guide**
  - Create `docs/admin-style-guide.md`
  - Design tokens (shared with widget where possible)
  - Component specifications
  - Form patterns
  - Table/list patterns
  - Navigation patterns

- [ ] **UI Modernization**
  - Convert to React (optional)
  - Consistent styling with widget
  - Better UX for data ingestion
  - Improved job monitoring

- [ ] **New Features**
  - Dashboard overview
  - Analytics preview
  - Better error handling
  - Bulk operations

### Notes
- Lower priority than widget v2
- Can be done by separate developer
- Should share design tokens with widget

---

## Phase 4: Pilot Integration

### Completed

- [x] **Test Customer Created**
  - Site ID: `test`
  - API Key: `zk_live_test_L9dcIYzWTZxwoU-zKk6RMwTbf526hAPR`
  - Allowed Domains: localhost, 127.0.0.1

### Blocked

- [ ] **Admizz Education Setup**
  - Status: ⏸️ BLOCKED
  - Blocker: OpenAI credits (need to test ingestion first)
  - Tasks:
    - [ ] Create customer record
    - [ ] Ingest country pages, FAQs
    - [ ] Configure professional tone
    - [ ] Generate embed code
    - [ ] Test on their website

- [ ] **Khems Cleaning Setup**
  - Status: ⏸️ BLOCKED
  - Blocker: OpenAI credits
  - Tasks:
    - [ ] Create customer record
    - [ ] Ingest services, pricing pages
    - [ ] Configure friendly tone
    - [ ] Generate embed code
    - [ ] Test on their website

- [ ] **Guntabya (OTA) Setup**
  - Status: ⏸️ BLOCKED
  - Blocker: OpenAI credits
  - Tasks:
    - [ ] Create customer record
    - [ ] Ingest listings, policies
    - [ ] Configure neutral tone
    - [ ] Generate embed code
    - [ ] Test on their website

---

## Phase 5: Production Deployment

### Not Started

- [ ] **Backend Deployment**
  - Platform: Railway or Fly.io
  - Tasks:
    - [ ] Create production environment
    - [ ] Configure environment variables
    - [ ] Setup database connection
    - [ ] Deploy API
    - [ ] Configure domain (api.zunkiree.ai)

- [ ] **Widget Hosting**
  - Platform: Vercel or Cloudflare Pages
  - Tasks:
    - [ ] Build production bundle
    - [ ] Deploy to CDN
    - [ ] Configure domain (cdn.zunkiree.ai)

- [ ] **Security & Monitoring**
  - Tasks:
    - [ ] Setup Cloudflare (DDoS, rate limiting)
    - [ ] Configure CORS for production domains
    - [ ] Setup error logging
    - [ ] Setup uptime monitoring

- [ ] **DNS & SSL**
  - Tasks:
    - [ ] Configure zunkiree.ai domain
    - [ ] SSL certificates
    - [ ] CDN configuration

- [ ] **Documentation**
  - Tasks:
    - [ ] Customer onboarding guide
    - [ ] Embed code instructions
    - [ ] Troubleshooting guide

---

## Blockers & Dependencies

### Active Blockers

| ID | Blocker | Impact | Action Required | Owner |
|----|---------|--------|-----------------|-------|
| B1 | OpenAI API Credits | Testing, Pilot Setup | Add $5-10 at platform.openai.com | Sadin |

### Dependencies

```
OpenAI Credits (B1)
    └── Test Embeddings
        └── Test Query Flow
            └── Pilot Customer Setup
                └── Production Deployment
```

---

## Infrastructure Status

| Service | Status | Details |
|---------|--------|---------|
| Supabase (PostgreSQL) | 🟢 Ready | Project: zunkiree-search |
| Pinecone (Vector DB) | 🟢 Ready | Index: zunkiree-search |
| OpenAI API | 🔴 No Credits | Needs $5-10 |

### Credentials Location
All credentials stored in: `backend/.env`

---

## Quick Start Commands

```bash
# Backend (requires OpenAI credits for full functionality)
cd backend && venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Widget Dev Server
cd widget && npm run dev

# Admin Panel
cd admin && py -m http.server 3000
```

---

## What Can Be Done Without OpenAI Credits

| Task | Possible? | Notes |
|------|-----------|-------|
| Start backend server | ✅ Yes | API will load, docs available at /docs |
| View admin panel | ✅ Yes | UI fully functional |
| Create customers | ✅ Yes | Database operations work |
| Configure widgets | ✅ Yes | Settings saved to database |
| Widget UI testing | ✅ Yes | UI renders, but queries will fail |
| Ingest data | ❌ No | Requires embeddings |
| Query/search | ❌ No | Requires LLM |

---

## Future Enhancements (Post-v1)

### Priority 1 (After Pilot Success)
- [ ] Analytics dashboard
- [ ] Query logs viewer
- [ ] Usage metrics per customer

### Priority 2 (Scale)
- [ ] Self-serve customer onboarding
- [ ] Stripe payment integration
- [ ] Multi-language support

### Priority 3 (Advanced)
- [ ] Query complexity routing (auto-select model)
- [ ] Anthropic Claude provider
- [ ] Azure OpenAI provider
- [ ] Custom fine-tuned models
- [ ] Conversation memory (multi-turn)

### Ideas Backlog
- [ ] Voice input
- [ ] Widget themes marketplace
- [ ] API for programmatic access
- [ ] Slack/Discord integrations
- [ ] Scheduled re-indexing

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| [zunkiree-search-v1.md](../zunkiree-search-v1.md) | Original specification |
| [architecture.md](architecture.md) | System architecture |
| [api-spec.md](api-spec.md) | API documentation |
| [database-schema.md](database-schema.md) | Database tables |
| [widget-spec.md](widget-spec.md) | Widget specifications |
| [llm-abstraction.md](llm-abstraction.md) | LLM strategy |
| [implementation-plan.md](implementation-plan.md) | Build phases |
| [session-log.md](../session-log/session-log.md) | Development history |

---

## Changelog

### December 26, 2024
- Implemented LLM abstraction layer
- Changed default model to gpt-4o-mini
- Created project-roadmap.md

### December 25, 2024
- Completed all code implementation
- Widget bundle created (149KB)
- Admin panel completed
- Test customer created
- Identified OpenAI credits as blocker

---

*This roadmap should be updated as tasks are completed or new requirements emerge.*
