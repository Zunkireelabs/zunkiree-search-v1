# Zunkiree Search - Production Deployment Plan

## Objective
Deploy Zunkiree Search to production so it can be embedded on customer websites.

## Architecture Overview
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Customer Site  │────▶│  Widget (CDN)   │────▶│  Backend API    │
│  (Any website)  │     │  Vercel         │     │  Railway        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                              ┌─────────────────────────┼─────────────────────────┐
                              ▼                         ▼                         ▼
                        ┌──────────┐            ┌──────────────┐           ┌──────────┐
                        │ Supabase │            │   Pinecone   │           │  OpenAI  │
                        │ Postgres │            │ Vector Store │           │   API    │
                        └──────────┘            └──────────────┘           └──────────┘
```

---

## Phase 1: Backend Deployment (Railway)

### Step 1.1: Create Deployment Files
Create `backend/Procfile`:
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Step 1.2: Deploy to Railway
1. Go to https://railway.app and create new project
2. Connect GitHub repo OR use Railway CLI
3. Set root directory to `/backend`
4. Configure environment variables:

| Variable | Value |
|----------|-------|
| `OPENAI_API_KEY` | sk-... (your key) |
| `PINECONE_API_KEY` | pcsk_... (your key) |
| `PINECONE_HOST` | https://...svc.pinecone.io |
| `PINECONE_INDEX_NAME` | zunkiree-search |
| `DATABASE_URL` | postgresql+asyncpg://... (Supabase) |
| `API_SECRET_KEY` | (generate secure random string) |
| `ALLOWED_ORIGINS` | https://dev-web.zunkireelabs.com,https://cdn.vercel.app |

### Step 1.3: Note Railway URL
After deployment, Railway provides URL like:
`https://zunkiree-search-production.up.railway.app`

---

## Phase 2: Widget Deployment (Vercel CDN)

### Step 2.1: Create Vercel Config
Create `widget/vercel.json`:
```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Access-Control-Allow-Origin", "value": "*" },
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    }
  ]
}
```

### Step 2.2: Deploy to Vercel
1. Go to https://vercel.com and create new project
2. Connect GitHub repo OR use Vercel CLI
3. Set root directory to `/widget`
4. Deploy

### Step 2.3: Note Vercel URL
After deployment, Vercel provides URL like:
`https://zunkiree-widget.vercel.app/zunkiree-widget.iife.js`

---

## Phase 3: Create Customer Sites

### Step 3.1: Create 4 Customer Entries via API

Once backend is live, call `POST /api/v1/admin/customers` for each:

**1. ZunkireeLabs (Client #0)**
```json
{
  "name": "ZunkireeLabs",
  "site_id": "zunkireelabs",
  "allowed_domains": ["dev-web.zunkireelabs.com", "zunkireelabs.com", "www.zunkireelabs.com"]
}
```

**2. Admizz**
```json
{
  "name": "Admizz",
  "site_id": "admizz",
  "allowed_domains": ["admizz.com", "www.admizz.com"]
}
```

**3. Khems Cleaning**
```json
{
  "name": "Khems Cleaning",
  "site_id": "khems",
  "allowed_domains": ["khemscleaning.com", "www.khemscleaning.com"]
}
```

**4. Guntabya**
```json
{
  "name": "Guntabya",
  "site_id": "guntabya",
  "allowed_domains": ["guntabya.com", "www.guntabya.com"]
}
```

---

## Phase 4: Embed Widget on ZunkireeLabs Website

### Step 4.1: Add to dev-web.zunkireelabs.com
Add this snippet to your Next.js site (e.g., in a component or page):

```html
<!-- Zunkiree Search Widget -->
<div id="zunkiree-search"></div>
<script
  src="https://zunkiree-widget.vercel.app/zunkiree-widget.iife.js"
  data-site-id="zunkireelabs"
  data-api-url="https://zunkiree-search-production.up.railway.app"
  data-mode="hero"
  data-border-radius="rounded"
></script>
```

### Step 4.2: For Next.js Specifically
Create a component or use `next/script`:
```tsx
import Script from 'next/script'

export default function ZunkireeDemo() {
  return (
    <>
      <div id="zunkiree-search" />
      <Script
        src="https://zunkiree-widget.vercel.app/zunkiree-widget.iife.js"
        data-site-id="zunkireelabs"
        data-api-url="https://zunkiree-search-production.up.railway.app"
        data-mode="hero"
        strategy="lazyOnload"
      />
    </>
  )
}
```

---

## Phase 5: Ingest Content for ZunkireeLabs

After customer is created, ingest content via admin panel or API:
- Company website pages
- Product documentation
- FAQ content

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `backend/Procfile` | CREATE | Railway deployment config |
| `widget/vercel.json` | CREATE | Vercel CDN config with CORS headers |
| `backend/.env` | UPDATE | Production environment variables |

---

## Execution Order

1. Create `backend/Procfile`
2. Deploy backend to Railway
3. Update `ALLOWED_ORIGINS` with Railway URL
4. Create `widget/vercel.json`
5. Deploy widget to Vercel
6. Create 4 customer entries via API
7. Embed widget on dev-web.zunkireelabs.com
8. Ingest content for zunkireelabs site
9. Test end-to-end

---

## Expected URLs After Deployment

| Service | URL |
|---------|-----|
| Backend API | https://zunkiree-search-xxx.up.railway.app |
| Widget CDN | https://zunkiree-widget.vercel.app/zunkiree-widget.iife.js |
| API Docs | https://zunkiree-search-xxx.up.railway.app/docs |

---

## Embed Code Template for Customers

```html
<div id="zunkiree-search"></div>
<script
  src="https://zunkiree-widget.vercel.app/zunkiree-widget.iife.js"
  data-site-id="YOUR_SITE_ID"
  data-api-url="https://zunkiree-search-xxx.up.railway.app"
  data-mode="hero"
></script>
```
