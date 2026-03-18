---
name: deploy-reader
description: Read and summarize the Zunkiree Search deployment setup. Covers how the widget (Vercel) and backend (Railway) deploy, which branch triggers auto-deploy, key config files, environment variables, and the full CI/CD pipeline. Use when you need to understand deployment, check what's live, figure out why changes aren't showing, or plan a release.
---

# Deploy Reader — Zunkiree Search

You are reading the deployment architecture for Zunkiree Search so you can answer questions about how code gets to production.

## Deployment Architecture

```
zunkiree-search-v1/ (monorepo)
├── widget/   → Vercel CDN    (auto-deploy from main)
├── backend/  → Railway       (auto-deploy from main)
├── admin/    → Vercel         (static, auto-deploy from main)
└── dashboard/→ Vercel         (static, auto-deploy from main)
```

### Widget (Frontend)

- **Host:** Vercel
- **URL:** `https://zunkiree-widget.vercel.app/zunkiree-widget.iife.js`
- **Auto-deploy trigger:** Push to `main` branch
- **Build command:** `npm run build` (Vite, outputs single IIFE file)
- **Output:** `widget/dist/zunkiree-widget.iife.js`
- **Config:** `widget/vercel.json` (CORS `Access-Control-Allow-Origin: *`, `Cache-Control: must-revalidate`)
- **Root directory in Vercel:** `/widget`

**Key point:** Only pushes to `main` trigger a Vercel deploy. Feature branches do NOT auto-deploy. Changes must be merged to `main` first.

### Backend (API)

- **Host:** Railway
- **URL:** `https://zunkiree-search-production.up.railway.app`
- **Auto-deploy trigger:** Push to `main` branch
- **Build:** Nixpacks (reads `backend/Procfile` or `backend/railway.toml`)
- **Entry:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Root directory in Railway:** `/backend`
- **Config files:**
  - `backend/Procfile` — Railway start command
  - `backend/railway.toml` — build/deploy/restart policy
  - `backend/Dockerfile` — for Docker/VPS deployment (not used on Railway)

### VPS / Docker Compose (Alternative)

- **File:** `docker-compose.yml` at repo root
- **Network:** External `hosting` network with Traefik reverse proxy
- **Domain:** `api.zunkireelabs.com` (via Traefik labels)
- **Health check:** `GET /health` on port 8000

## How to Deploy

### Automatic (standard workflow)
```bash
git checkout main
git merge <feature-branch>
git push origin main
# Widget deploys to Vercel in ~60s
# Backend deploys to Railway in ~2-3 min
```

### Manual
```bash
# Widget
cd widget && npm run build && vercel deploy

# Backend
cd backend && railway deploy
```

## Key Config Files

| File | Purpose |
|------|---------|
| `widget/vercel.json` | Vercel build + CORS headers |
| `widget/vite.config.ts` | IIFE bundle output config |
| `backend/Procfile` | Railway start command |
| `backend/railway.toml` | Railway build/deploy/restart |
| `backend/Dockerfile` | Docker image (VPS path) |
| `backend/.env` | All secrets and API keys |
| `docker-compose.yml` | VPS orchestration + Traefik |
| `scripts/backup.sh` | PostgreSQL backup automation |

## Environment Variables (Backend)

Required in Railway dashboard or `backend/.env`:
- `OPENAI_API_KEY` — LLM access
- `PINECONE_API_KEY`, `PINECONE_HOST`, `PINECONE_INDEX_NAME` — Vector DB
- `DATABASE_URL` — Supabase PostgreSQL (asyncpg)
- `API_SECRET_KEY` — Auth
- `ALLOWED_ORIGINS` — CORS whitelist
- `LLM_MODEL`, `LLM_MODEL_PREMIUM` — Model selection
- `SMTP_*` — Email verification

## External Services

| Service | Purpose |
|---------|---------|
| Vercel | Widget CDN hosting |
| Railway | Backend API hosting |
| Supabase | PostgreSQL database |
| Pinecone | Vector search (per-tenant namespaces) |
| OpenAI | LLM (gpt-4o-mini / gpt-4o) |
| Cloudflare | CDN + DDoS protection |

## Common Debugging

**"Changes aren't showing after push"**
1. Check which branch you pushed — only `main` triggers auto-deploy
2. Check Vercel dashboard for build status
3. Widget has `Cache-Control: must-revalidate` so hard refresh should work
4. Try `curl -I https://zunkiree-widget.vercel.app/zunkiree-widget.iife.js` to check headers

**"Backend API not responding"**
1. Check Railway dashboard for deploy status and logs
2. Hit health endpoint: `GET /health`
3. Check if env vars are set in Railway

## Execution Rules

1. Read the relevant config files before answering deployment questions
2. Always check which branch the user is on — `main` is the only auto-deploy branch
3. Never modify `.env` files or secrets without explicit user confirmation
4. When suggesting deploys, remind the user to merge to `main` first if on a feature branch
