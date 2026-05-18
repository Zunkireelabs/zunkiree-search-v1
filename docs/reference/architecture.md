# Zunkiree Search v1 - System Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER'S WEBSITE                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Zunkiree Widget (Embedded)                       │   │
│  │  ┌─────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │   │
│  │  │ Trigger │  │ Chat Window  │  │  Messages   │  │ Input Field  │  │   │
│  │  │ Button  │  │              │  │             │  │              │  │   │
│  │  └─────────┘  └──────────────┘  └─────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ HTTPS
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLOUDFLARE (CDN + Security)                        │
│                    Rate Limiting, DDoS Protection, SSL                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ZUNKIREE API (FastAPI)                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Query Service  │  │ Ingestion Svc   │  │     Admin Service           │  │
│  │                 │  │                 │  │                             │  │
│  │ - Embed query   │  │ - Crawl URLs    │  │ - Upload docs               │  │
│  │ - Retrieve docs │  │ - Parse PDFs    │  │ - Trigger re-index          │  │
│  │ - Build prompt  │  │ - Chunk text    │  │ - Update config             │  │
│  │ - Call LLM      │  │ - Embed chunks  │  │                             │  │
│  │ - Validate resp │  │ - Store vectors │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
         │                      │                        │
         │                      │                        │
         ▼                      ▼                        ▼
┌─────────────┐  ┌─────────────────────┐  ┌────────────────────────────────────┐
│   OPENAI    │  │      PINECONE       │  │           SUPABASE                 │
│             │  │                     │  │                                    │
│ - gpt-4o-   │  │ - Vector storage    │  │ - PostgreSQL (configs, metadata)  │
│   mini      │  │ - Namespace/tenant  │  │ - Customer records                │
│ - Embeddings│  │ - Semantic search   │  │ - Widget configs                  │
└─────────────┘  └─────────────────────┘  └────────────────────────────────────┘
                                                         │
                                                         ▼
                                          ┌────────────────────────────────────┐
                                          │        CLOUDFLARE R2               │
                                          │                                    │
                                          │ - Uploaded PDFs                    │
                                          │ - Document storage                 │
                                          └────────────────────────────────────┘
```

---

## Request Flow: User Query

```
1. User types question in widget
         │
         ▼
2. Widget sends POST /api/v1/query
   {
     "site_id": "admizz",
     "question": "What are the requirements for Canada?"
   }
         │
         ▼
3. API validates request
   - Check site_id exists
   - Validate origin domain
   - Rate limit check
         │
         ▼
4. Generate query embedding
   - OpenAI text-embedding-3-large
   - 3072 dimensions
         │
         ▼
5. Retrieve relevant chunks
   - Pinecone query (namespace=site_id)
   - Top 5 chunks by similarity
         │
         ▼
6. Build grounded prompt
   - System prompt with brand/tone
   - Retrieved context
   - User question
         │
         ▼
7. Call LLM
   - OpenAI gpt-4o-mini (default)
   - Temperature: 0.3
   - Max tokens: 500
   - See [LLM Abstraction](llm-abstraction.md)
         │
         ▼
8. Validate & format response
   - Check for hallucination markers
   - Format as markdown
   - Generate follow-up suggestions
         │
         ▼
9. Return to widget
   {
     "answer": "...",
     "suggestions": ["...", "..."]
   }
```

---

## Data Ingestion Flow

```
1. Admin triggers ingestion
   - URL crawl OR document upload
         │
         ▼
2. Create ingestion job record
   - Status: "pending"
   - Store in PostgreSQL
         │
         ▼
3. Fetch content
   - URL: httpx + BeautifulSoup
   - PDF: pdfplumber
         │
         ▼
4. Extract text
   - Clean HTML/boilerplate
   - Extract meaningful content
         │
         ▼
5. Chunk text
   - ~500 tokens per chunk
   - 50 token overlap
   - Respect sentence boundaries
         │
         ▼
6. Generate embeddings
   - Batch embed chunks
   - OpenAI text-embedding-3-large
         │
         ▼
7. Store in Pinecone
   - Namespace = customer_id
   - Metadata: source_url, chunk_index
         │
         ▼
8. Update job status
   - Status: "completed"
   - Store chunk metadata in PostgreSQL
```

---

## Multi-Tenancy Design

Each customer (tenant) is isolated by:

1. **Pinecone Namespace**: Vectors stored in separate namespaces
   - `admizz` namespace
   - `khems` namespace
   - `guntabya` namespace

2. **Domain Allowlist**: Only allowed domains can query
   - Customer A: `admizz.com`, `www.admizz.com`
   - Customer B: `khemsclean.com`

3. **API Key**: Each customer has unique site_id
   - Used for authentication
   - Used for config lookup

4. **Config Isolation**: Separate widget configs per customer
   - Brand name
   - Tone (formal/neutral/friendly)
   - Primary color
   - Allowed topics

---

## Security Model

```
┌────────────────────────────────────────────────┐
│                 SECURITY LAYERS                 │
├────────────────────────────────────────────────┤
│ 1. Cloudflare                                  │
│    - DDoS protection                           │
│    - Rate limiting (100 req/min per IP)        │
│    - WAF rules                                 │
├────────────────────────────────────────────────┤
│ 2. Origin Validation                           │
│    - Check request Origin header               │
│    - Match against customer's allowed domains  │
├────────────────────────────────────────────────┤
│ 3. API Key Validation                          │
│    - site_id must exist in database            │
│    - Admin endpoints require secret key        │
├────────────────────────────────────────────────┤
│ 4. Input Sanitization                          │
│    - Limit query length (500 chars)            │
│    - Strip malicious content                   │
├────────────────────────────────────────────────┤
│ 5. Output Validation                           │
│    - LLM response validation                   │
│    - No PII leakage                            │
└────────────────────────────────────────────────┘
```

---

## Technology Stack Summary

| Layer | Technology | Purpose |
|-------|------------|---------|
| CDN | Cloudflare | Security, caching, SSL |
| API | FastAPI (Python) | Backend services |
| Database | Supabase PostgreSQL | Configs, metadata |
| Vector DB | Pinecone | Semantic search |
| LLM | OpenAI gpt-4o-mini / gpt-4o | Answer generation - See [LLM Abstraction](llm-abstraction.md) |
| Embeddings | text-embedding-3-large | Vector generation |
| Object Storage | Cloudflare R2 | Document storage |
| Widget | React + Vite | Embeddable UI |
| Widget Hosting | Vercel/Cloudflare Pages | Static hosting |
| API Hosting | Railway/Fly.io | Container hosting |
