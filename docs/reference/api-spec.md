# Zunkiree Search v1 - API Specification

## Base URL
```
Production: https://api.zunkiree.ai/api/v1
Development: http://localhost:8000/api/v1
```

---

## Public Endpoints (Widget)

### Query - Submit Question

Submit a natural language question and receive an AI-generated answer.

```http
POST /query
Content-Type: application/json
Origin: https://customer-domain.com
```

**Request Body:**
```json
{
  "site_id": "admizz",
  "question": "What are the requirements for studying in Canada?"
}
```

**Response (200 OK):**
```json
{
  "answer": "To study in Canada, you typically need...",
  "suggestions": [
    "What is the application process?",
    "What are the tuition fees?"
  ],
  "sources": [
    {
      "title": "Canada Study Guide",
      "url": "https://admizz.com/canada"
    }
  ]
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| 400 | Invalid request (missing fields, question too long) |
| 401 | Invalid site_id |
| 403 | Origin domain not allowed |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

**Error Response Format:**
```json
{
  "error": {
    "code": "INVALID_ORIGIN",
    "message": "Origin domain is not allowed for this site"
  }
}
```

---

### Widget Config - Get Configuration

Retrieve widget configuration for a site.

```http
GET /widget/config/{site_id}
Origin: https://customer-domain.com
```

**Response (200 OK):**
```json
{
  "brand_name": "Admizz Education",
  "primary_color": "#2563eb",
  "tone": "professional",
  "placeholder_text": "Ask about studying abroad...",
  "welcome_message": "Hi! How can I help you today?"
}
```

---

## Admin Endpoints (Internal)

All admin endpoints require authentication via header:
```http
X-Admin-Key: {admin_secret_key}
```

### Ingest URL - Crawl Website

```http
POST /admin/ingest/url
X-Admin-Key: {admin_secret_key}
Content-Type: application/json
```

**Request Body:**
```json
{
  "customer_id": "admizz",
  "url": "https://admizz.com/canada",
  "depth": 1,
  "max_pages": 10
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "job_abc123",
  "status": "pending",
  "message": "Ingestion job created"
}
```

---

### Ingest Document - Upload File

```http
POST /admin/ingest/document
X-Admin-Key: {admin_secret_key}
Content-Type: multipart/form-data
```

**Form Fields:**
- `customer_id`: string (required)
- `file`: binary (required) - PDF, TXT, or DOCX
- `title`: string (optional)

**Response (202 Accepted):**
```json
{
  "job_id": "job_def456",
  "status": "pending",
  "message": "Document upload initiated"
}
```

---

### Re-index Customer - Trigger Full Re-index

```http
POST /admin/reindex/{customer_id}
X-Admin-Key: {admin_secret_key}
```

**Response (202 Accepted):**
```json
{
  "job_id": "job_ghi789",
  "status": "pending",
  "message": "Re-index job created"
}
```

---

### Update Config - Modify Widget Settings

```http
PUT /admin/config/{customer_id}
X-Admin-Key: {admin_secret_key}
Content-Type: application/json
```

**Request Body:**
```json
{
  "brand_name": "Admizz Education",
  "tone": "professional",
  "primary_color": "#2563eb",
  "allowed_topics": ["study abroad", "visa", "universities"],
  "fallback_message": "I don't have that information yet. Please contact our counselors."
}
```

**Response (200 OK):**
```json
{
  "message": "Config updated successfully"
}
```

---

### Get Jobs - List Ingestion Jobs

```http
GET /admin/jobs/{customer_id}?status=pending&limit=10
X-Admin-Key: {admin_secret_key}
```

**Query Parameters:**
- `status`: Filter by status (pending, processing, completed, failed)
- `limit`: Max results (default: 20)
- `offset`: Pagination offset

**Response (200 OK):**
```json
{
  "jobs": [
    {
      "id": "job_abc123",
      "source_type": "url",
      "source_url": "https://admizz.com/canada",
      "status": "completed",
      "chunks_created": 25,
      "created_at": "2024-01-15T10:30:00Z",
      "completed_at": "2024-01-15T10:32:15Z"
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

---

### Create Customer - Add New Customer

```http
POST /admin/customers
X-Admin-Key: {admin_secret_key}
Content-Type: application/json
```

**Request Body:**
```json
{
  "name": "Admizz Education",
  "site_id": "admizz",
  "allowed_domains": ["admizz.com", "www.admizz.com"]
}
```

**Response (201 Created):**
```json
{
  "id": "cust_xyz123",
  "site_id": "admizz",
  "api_key": "zk_live_abc123...",
  "message": "Customer created successfully"
}
```

---

### Health Check

```http
GET /health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "database": "connected",
    "pinecone": "connected",
    "openai": "connected"
  }
}
```

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| POST /query | 60 requests/minute per site |
| GET /widget/config | 100 requests/minute per site |
| Admin endpoints | 100 requests/minute total |

---

## Error Codes

| Code | Description |
|------|-------------|
| INVALID_REQUEST | Malformed request body |
| INVALID_SITE_ID | Site ID does not exist |
| INVALID_ORIGIN | Origin domain not in allowlist |
| RATE_LIMITED | Too many requests |
| QUESTION_TOO_LONG | Question exceeds 500 characters |
| INGESTION_FAILED | Document processing failed |
| LLM_ERROR | LLM service unavailable |
| INTERNAL_ERROR | Unexpected server error |

---

## LLM Configuration

The LLM model is configurable via environment variables. See [LLM Abstraction](llm-abstraction.md) for details.

| Setting | Default | Description |
|---------|---------|-------------|
| LLM_MODEL | gpt-4o-mini | Default model for queries |
| LLM_MODEL_PREMIUM | gpt-4o | Premium model (future use) |

Model selection is handled by the backend abstraction layer - no API changes required.
