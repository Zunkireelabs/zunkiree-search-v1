# Zunkiree Search v1 - Database Schema

## Database: PostgreSQL (Supabase)

---

## Tables Overview

```
┌─────────────────┐       ┌─────────────────┐
│   customers     │───┬──▶│     domains     │
└─────────────────┘   │   └─────────────────┘
         │            │
         │            │   ┌─────────────────┐
         │            ├──▶│ widget_configs  │
         │            │   └─────────────────┘
         │            │
         │            │   ┌─────────────────┐
         │            ├──▶│ ingestion_jobs  │
         │            │   └─────────────────┘
         │            │           │
         │            │           ▼
         │            │   ┌─────────────────┐
         │            └──▶│ document_chunks │
         │                └─────────────────┘
         │
         │            ┌─────────────────┐
         └───────────▶│   query_logs    │
                      └─────────────────┘
```

---

## Table: customers

Primary table for customer/tenant information.

```sql
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    site_id VARCHAR(50) UNIQUE NOT NULL,
    api_key VARCHAR(255) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_customers_site_id ON customers(site_id);
CREATE INDEX idx_customers_api_key ON customers(api_key);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(255) | Customer display name |
| site_id | VARCHAR(50) | Unique identifier used in widget (e.g., "admizz") |
| api_key | VARCHAR(255) | Secret API key for authentication |
| is_active | BOOLEAN | Whether customer is active |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last update time |

---

## Table: domains

Allowed domains for each customer (CORS/origin validation).

```sql
CREATE TABLE domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    domain VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(customer_id, domain)
);

-- Indexes
CREATE INDEX idx_domains_customer_id ON domains(customer_id);
CREATE INDEX idx_domains_domain ON domains(domain);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| customer_id | UUID | Foreign key to customers |
| domain | VARCHAR(255) | Allowed domain (e.g., "admizz.com") |
| is_active | BOOLEAN | Whether domain is active |
| created_at | TIMESTAMP | Record creation time |

---

## Table: widget_configs

Widget appearance and behavior configuration.

```sql
CREATE TABLE widget_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID UNIQUE NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    brand_name VARCHAR(255) NOT NULL,
    tone VARCHAR(50) DEFAULT 'neutral',
    primary_color VARCHAR(7) DEFAULT '#2563eb',
    placeholder_text VARCHAR(255) DEFAULT 'Ask a question...',
    welcome_message TEXT,
    fallback_message TEXT DEFAULT 'I don''t have that information yet.',
    allowed_topics TEXT[],
    max_response_length INTEGER DEFAULT 500,
    show_sources BOOLEAN DEFAULT true,
    show_suggestions BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index
CREATE INDEX idx_widget_configs_customer_id ON widget_configs(customer_id);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| customer_id | UUID | Foreign key to customers (1:1) |
| brand_name | VARCHAR(255) | Display name in widget |
| tone | VARCHAR(50) | Response tone: formal, neutral, friendly |
| primary_color | VARCHAR(7) | Hex color code |
| placeholder_text | VARCHAR(255) | Input placeholder text |
| welcome_message | TEXT | Initial message shown to user |
| fallback_message | TEXT | Message when no answer found |
| allowed_topics | TEXT[] | Array of allowed topic keywords |
| max_response_length | INTEGER | Max tokens for LLM response |
| show_sources | BOOLEAN | Show source links in response |
| show_suggestions | BOOLEAN | Show follow-up suggestions |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last update time |

---

## Table: ingestion_jobs

Track document ingestion jobs.

```sql
CREATE TABLE ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL,
    source_url TEXT,
    source_filename VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending',
    chunks_created INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_ingestion_jobs_customer_id ON ingestion_jobs(customer_id);
CREATE INDEX idx_ingestion_jobs_status ON ingestion_jobs(status);
CREATE INDEX idx_ingestion_jobs_created_at ON ingestion_jobs(created_at DESC);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| customer_id | UUID | Foreign key to customers |
| source_type | VARCHAR(20) | Type: url, pdf, text |
| source_url | TEXT | URL if web crawl |
| source_filename | VARCHAR(255) | Filename if upload |
| status | VARCHAR(20) | pending, processing, completed, failed |
| chunks_created | INTEGER | Number of chunks generated |
| error_message | TEXT | Error details if failed |
| started_at | TIMESTAMP | Processing start time |
| completed_at | TIMESTAMP | Processing end time |
| created_at | TIMESTAMP | Job creation time |

---

## Table: document_chunks

Metadata for document chunks (vectors stored in Pinecone).

```sql
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
    vector_id VARCHAR(255) NOT NULL,
    chunk_index INTEGER NOT NULL,
    content_preview VARCHAR(500),
    source_url TEXT,
    source_title VARCHAR(255),
    token_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_document_chunks_customer_id ON document_chunks(customer_id);
CREATE INDEX idx_document_chunks_job_id ON document_chunks(job_id);
CREATE INDEX idx_document_chunks_vector_id ON document_chunks(vector_id);
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| customer_id | UUID | Foreign key to customers |
| job_id | UUID | Foreign key to ingestion_jobs |
| vector_id | VARCHAR(255) | ID in Pinecone |
| chunk_index | INTEGER | Position in original document |
| content_preview | VARCHAR(500) | First 500 chars of chunk |
| source_url | TEXT | Original source URL |
| source_title | VARCHAR(255) | Document/page title |
| token_count | INTEGER | Approximate token count |
| created_at | TIMESTAMP | Record creation time |

---

## Table: query_logs

Log all queries for debugging and analytics (future).

```sql
CREATE TABLE query_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT,
    chunks_used INTEGER,
    response_time_ms INTEGER,
    origin_domain VARCHAR(255),
    user_agent TEXT,
    ip_hash VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_query_logs_customer_id ON query_logs(customer_id);
CREATE INDEX idx_query_logs_created_at ON query_logs(created_at DESC);

-- Partition by month for performance (optional)
-- CREATE TABLE query_logs_2024_01 PARTITION OF query_logs
--     FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| customer_id | UUID | Foreign key to customers |
| question | TEXT | User's question |
| answer | TEXT | Generated answer |
| chunks_used | INTEGER | Number of context chunks used |
| response_time_ms | INTEGER | Total response time |
| origin_domain | VARCHAR(255) | Request origin |
| user_agent | TEXT | Browser user agent |
| ip_hash | VARCHAR(64) | Hashed IP for rate limiting |
| created_at | TIMESTAMP | Query timestamp |

---

## Initial Data: Pilot Customers

```sql
-- Insert pilot customers
INSERT INTO customers (name, site_id, api_key) VALUES
    ('Admizz Education', 'admizz', 'zk_live_admizz_' || gen_random_uuid()),
    ('Khems Cleaning', 'khems', 'zk_live_khems_' || gen_random_uuid()),
    ('Guntabya', 'guntabya', 'zk_live_guntabya_' || gen_random_uuid());

-- Insert domains
INSERT INTO domains (customer_id, domain)
SELECT id, 'admizz.com' FROM customers WHERE site_id = 'admizz'
UNION ALL
SELECT id, 'www.admizz.com' FROM customers WHERE site_id = 'admizz'
UNION ALL
SELECT id, 'khemsclean.com' FROM customers WHERE site_id = 'khems'
UNION ALL
SELECT id, 'guntabya.com' FROM customers WHERE site_id = 'guntabya';

-- Insert widget configs
INSERT INTO widget_configs (customer_id, brand_name, tone)
SELECT id, 'Admizz Education', 'professional' FROM customers WHERE site_id = 'admizz'
UNION ALL
SELECT id, 'Khems Cleaning', 'friendly' FROM customers WHERE site_id = 'khems'
UNION ALL
SELECT id, 'Guntabya', 'neutral' FROM customers WHERE site_id = 'guntabya';
```

---

## Migration Order

1. Create `customers` table
2. Create `domains` table
3. Create `widget_configs` table
4. Create `ingestion_jobs` table
5. Create `document_chunks` table
6. Create `query_logs` table
7. Insert pilot customer data
