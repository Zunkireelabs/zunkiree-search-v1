# Zunkiree Search - Deployment Architecture

## Overview

Multi-environment deployment pipeline for the Zunkiree Search monorepo. Supports team collaboration with automated quality gates, environment isolation, and zero-downtime deployments.

```
feature/* ──PR──> develop ──PR──> staging ──PR──> main (production)
                    │                │                │
                    ▼                ▼                ▼
              Dev Environment   Staging Env     Production Env
```

**Environments**: 3 (dev, staging, production)
**Deployable Units**: 4 (backend, widget, admin, dashboard)
**CI/CD**: GitHub Actions
**Container Registry**: GitHub Container Registry (GHCR)
**Additional Cost**: $0

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         GitHub Repository                            │
│  Zunkireelabs/zunkiree-search-v1                                     │
│                                                                      │
│  Branches:  feature/* ──> develop ──> staging ──> main               │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    GitHub Actions CI/CD                          │ │
│  │  ci.yml ─────────────── Lint, build, test on every PR           │ │
│  │  deploy-backend.yml ─── Build image → GHCR → SSH deploy to VPS │ │
│  │  migrate.yml ────────── Manual migration dispatch               │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
         │                              │
         │ Docker images (GHCR)         │ Git push triggers
         ▼                              ▼
┌─────────────────────┐     ┌──────────────────────────┐
│     VPS Server      │     │     Vercel Platform      │
│   (Docker+Traefik)  │     │   (Auto branch deploy)   │
│                     │     │                          │
│ ┌─────────────────┐ │     │ Widget  → CDN (IIFE.js) │
│ │ zunkiree-api-   │ │     │ Admin   → Static HTML   │
│ │ prod / staging  │ │     │ Dashboard → Static HTML  │
│ │ / dev           │ │     │                          │
│ └────────┬────────┘ │     └──────────────────────────┘
│          │          │
│   Traefik (SSL)     │
│   ├─ api.zunkireelabs.com         → prod
│   ├─ api-staging.zunkireelabs.com → staging
│   └─ api-dev.zunkireelabs.com     → dev
└─────────┬───────────┘
          │
    ┌─────┴──────────────────────────────────────┐
    │              External Services              │
    │                                             │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
    │  │ Supabase │  │ Pinecone │  │  OpenAI  │ │
    │  │ PostgreSQL│  │ Vector DB│  │ LLM/Emb  │ │
    │  │          │  │          │  │          │ │
    │  │ Schemas: │  │ Prefix:  │  │ Shared   │ │
    │  │ public   │  │ (none)   │  │ API key  │ │
    │  │ staging  │  │ staging- │  │          │ │
    │  │ dev      │  │ dev-     │  │          │ │
    │  └──────────┘  └──────────┘  └──────────┘ │
    └────────────────────────────────────────────┘
```

---

## 1. Branching Strategy

### Branch Roles

| Branch | Purpose | Deploys To | Auto-Deploy? |
|--------|---------|------------|--------------|
| `main` | Production-ready code | Production environment | Yes, on merge |
| `staging` | Pre-production QA/testing | Staging environment | Yes, on merge |
| `develop` | Integration branch for features | Dev environment | Yes, on merge |
| `feature/*` | Individual feature work | Nothing (CI only) | No |
| `hotfix/*` | Emergency production fixes | Production (via PR to main) | Yes, on merge |

### Code Flow

**Normal feature development:**
```
1. Developer creates feature/xyz from develop
2. Developer works, commits, pushes
3. Opens PR: feature/xyz → develop (CI runs)
4. After review + CI pass → merge to develop → auto-deploys to dev
5. When ready for QA: PR develop → staging → auto-deploys to staging
6. After QA passes: PR staging → main → auto-deploys to production
```

**Hotfix (emergency production fix):**
```
1. Create hotfix/xyz from main
2. Fix the issue
3. PR hotfix/xyz → main (requires 1 approval)
4. After merge → auto-deploys to production
5. Cherry-pick fix back to develop
```

### Branch Protection Rules

**`main` (production):**
- Require pull request before merging
- Require 1 approval
- Require status checks to pass (backend-ci, widget-ci)
- Require branches to be up to date
- No force pushes
- No deletions

**`staging`:**
- Require pull request before merging
- Require status checks to pass
- Source: only `develop` branch

**`develop`:**
- Require pull request before merging
- Require status checks to pass
- No approval required (to avoid blocking solo developers)

---

## 2. Environment Architecture

### 2.1 Backend Environments (VPS - Docker + Traefik)

All three backend environments run on the same VPS as separate Docker containers. Traefik handles routing and SSL.

| Environment | Container Name | Domain | Port | Resources |
|-------------|---------------|--------|------|-----------|
| **Production** | `zunkiree-api-prod` | `api.zunkireelabs.com` | 8000 | No limits (full VPS resources) |
| **Staging** | `zunkiree-api-staging` | `api-staging.zunkireelabs.com` | 8000 | 0.5 CPU, 512MB RAM |
| **Dev** | `zunkiree-api-dev` | `api-dev.zunkireelabs.com` | 8000 | 0.25 CPU, 256MB RAM |

**DNS Records Required:**
```
api.zunkireelabs.com         → A → <VPS_IP>  (already exists)
api-staging.zunkireelabs.com → A → <VPS_IP>  (new)
api-dev.zunkireelabs.com     → A → <VPS_IP>  (new)
```

Traefik auto-provisions Let's Encrypt SSL certificates for each subdomain.

### 2.2 Frontend Environments (Vercel)

Vercel natively deploys each branch as a preview environment. No GitHub Actions needed.

| Environment | Branch | Widget URL | Admin/Dashboard URL |
|-------------|--------|------------|---------------------|
| **Production** | `main` | `zunkiree-search-v1.vercel.app` | `zunkiree-admin.vercel.app` |
| **Staging** | `staging` | Auto-generated Vercel preview URL | Auto-generated preview URL |
| **Dev** | `develop` | Auto-generated Vercel preview URL | Auto-generated preview URL |

### 2.3 External Service Isolation

All external services use the same account/project with logical isolation. Zero additional cost.

| Service | Production | Staging | Dev |
|---------|-----------|---------|-----|
| **Supabase PostgreSQL** | Schema: `public` | Schema: `staging` | Schema: `dev` |
| **Pinecone Vector DB** | Namespace: `{site_id}` | Namespace: `staging-{site_id}` | Namespace: `dev-{site_id}` |
| **OpenAI** | Shared API key | Shared API key | Shared API key |
| **Gmail SMTP** | Active | Disabled (or test) | Disabled |
| **eSewa/Khalti** | Live keys | Sandbox keys | Sandbox keys |

**Supabase Schema Isolation:**
```sql
-- One-time setup in Supabase SQL editor
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dev;
GRANT ALL ON SCHEMA staging TO postgres;
GRANT ALL ON SCHEMA dev TO postgres;
```

Each environment's `DATABASE_URL` includes the schema via `search_path`:
```
# Production
DATABASE_URL=postgresql://...?options=-c search_path=public

# Staging
DATABASE_URL=postgresql://...?options=-c search_path=staging

# Dev
DATABASE_URL=postgresql://...?options=-c search_path=dev
```

**Pinecone Namespace Isolation:**

Backend config includes `PINECONE_NAMESPACE_PREFIX` env var:
- Production: `""` (empty - backwards compatible)
- Staging: `"staging-"`
- Dev: `"dev-"`

The vector store prepends this prefix to all namespace operations.

---

## 3. CI/CD Pipeline (GitHub Actions)

### 3.1 Workflow: `ci.yml` - Quality Gate

Runs on every pull request to `develop`, `staging`, or `main`.

```
Trigger: pull_request → [develop, staging, main]

Jobs:
  backend-ci (runs when backend/** changed):
    ├── Checkout code
    ├── Setup Python 3.11
    ├── pip install -r backend/requirements.txt
    ├── pip install ruff
    ├── ruff check backend/
    └── pytest backend/tests/ (when tests exist)

  widget-ci (runs when widget/** changed):
    ├── Checkout code
    ├── Setup Node 20
    ├── cd widget && npm ci
    ├── npm run build
    └── Verify dist/zunkiree-widget.iife.js exists
```

### 3.2 Workflow: `deploy-backend.yml` - Backend Deployment

Runs on push to `develop`, `staging`, or `main` when backend files change.

```
Trigger: push → [develop, staging, main]
  paths: [backend/**, docker-compose.yml, scripts/**]

Environment mapping:
  develop → dev
  staging → staging
  main    → prod

Steps:
  1. Checkout code
  2. Login to GitHub Container Registry (GHCR)
  3. Build Docker image
     → ghcr.io/zunkireelabs/zunkiree-search-v1:{env}-latest
  4. Push image to GHCR
  5. SSH into VPS
  6. Run deploy script: scripts/deploy.sh {env}
     a. Tag current image as {env}-previous (rollback point)
     b. Pull new {env}-latest image
     c. Run pending migrations via scripts/migrate.py
     d. Restart container: docker compose --profile {env} up -d
  7. Health check: GET https://api-{env}.zunkireelabs.com/health
  8. On failure → SSH, run: scripts/deploy.sh {env} --rollback
```

### 3.3 Workflow: `migrate.yml` - Manual Migration Runner

Manual dispatch for running migrations against a specific environment.

```
Trigger: workflow_dispatch
  inputs:
    environment: [dev, staging, prod]

Steps:
  1. SSH into VPS
  2. Run migration container:
     docker run --rm --env-file envs/{env}.env \
       ghcr.io/zunkireelabs/zunkiree-search-v1:{env}-latest \
       python scripts/migrate.py
```

---

## 4. Docker Architecture

### 4.1 docker-compose.yml (Multi-Environment)

Single compose file with Docker profiles for each environment:

```yaml
services:
  # ── Production ─────────────────────────────────────
  zunkiree-api-prod:
    image: ghcr.io/zunkireelabs/zunkiree-search-v1:prod-latest
    container_name: zunkiree-api-prod
    restart: unless-stopped
    env_file: ./envs/prod.env
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.zunkiree-api-prod.rule=Host(`api.zunkireelabs.com`)"
      - "traefik.http.routers.zunkiree-api-prod.entrypoints=websecure"
      - "traefik.http.routers.zunkiree-api-prod.tls.certresolver=letsencrypt"
      - "traefik.http.services.zunkiree-api-prod.loadbalancer.server.port=8000"
    networks: [hosting]
    profiles: [prod]

  # ── Staging ────────────────────────────────────────
  zunkiree-api-staging:
    image: ghcr.io/zunkireelabs/zunkiree-search-v1:staging-latest
    container_name: zunkiree-api-staging
    restart: unless-stopped
    env_file: ./envs/staging.env
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.zunkiree-api-staging.rule=Host(`api-staging.zunkireelabs.com`)"
      - "traefik.http.routers.zunkiree-api-staging.entrypoints=websecure"
      - "traefik.http.routers.zunkiree-api-staging.tls.certresolver=letsencrypt"
      - "traefik.http.services.zunkiree-api-staging.loadbalancer.server.port=8000"
    networks: [hosting]
    profiles: [staging]

  # ── Dev ────────────────────────────────────────────
  zunkiree-api-dev:
    image: ghcr.io/zunkireelabs/zunkiree-search-v1:dev-latest
    container_name: zunkiree-api-dev
    restart: unless-stopped
    env_file: ./envs/dev.env
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 256M
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.zunkiree-api-dev.rule=Host(`api-dev.zunkireelabs.com`)"
      - "traefik.http.routers.zunkiree-api-dev.entrypoints=websecure"
      - "traefik.http.routers.zunkiree-api-dev.tls.certresolver=letsencrypt"
      - "traefik.http.services.zunkiree-api-dev.loadbalancer.server.port=8000"
    networks: [hosting]
    profiles: [dev]

  # ── Backup (unchanged) ────────────────────────────
  zunkiree-backup:
    image: postgres:16-alpine
    container_name: zunkiree-backup
    restart: "no"
    env_file: ./envs/prod.env
    volumes:
      - backup-data:/backups
      - ./scripts:/scripts:ro
    entrypoint: ["/bin/sh", "/scripts/backup.sh"]
    networks: [hosting]
    profiles: [backup]

volumes:
  backup-data:
    driver: local

networks:
  hosting:
    external: true
```

**Usage:**
```bash
# Start production
docker compose --profile prod up -d

# Start staging
docker compose --profile staging up -d

# Start dev
docker compose --profile dev up -d

# Start all environments
docker compose --profile prod --profile staging --profile dev up -d

# Run backup
docker compose --profile backup up
```

### 4.2 Dockerfile (Multi-Stage Build)

```dockerfile
# ── Stage 1: Dependencies ───────────────────────────
FROM python:3.11-slim AS deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Application ────────────────────────────
FROM python:3.11-slim
WORKDIR /app
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
COPY ../scripts/migrate.py /app/scripts/migrate.py
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.3 VPS Directory Structure

```
/opt/zunkiree/
├── docker-compose.yml        # Multi-environment compose file
├── envs/
│   ├── prod.env              # Production environment variables
│   ├── staging.env           # Staging environment variables
│   └── dev.env               # Dev environment variables
├── scripts/
│   ├── deploy.sh             # Deploy + rollback script
│   └── backup.sh             # Database backup script
└── backups/                  # Backup data volume mount
```

---

## 5. Secrets Management

### GitHub Repository Settings

**Environments** (Settings > Environments):
- `production` - used by deploy-backend.yml when branch=main
- `staging` - used by deploy-backend.yml when branch=staging
- `development` - used by deploy-backend.yml when branch=develop

**Repository-level secrets** (shared across all environments):

| Secret | Purpose |
|--------|---------|
| `VPS_HOST` | VPS IP address |
| `VPS_SSH_KEY` | SSH private key for deploy user |
| `VPS_SSH_USER` | SSH username (e.g., `deploy`) |

**Per-environment secrets:**

| Secret | Production | Staging | Dev |
|--------|-----------|---------|-----|
| `DATABASE_URL` | `...?search_path=public` | `...?search_path=staging` | `...?search_path=dev` |
| `OPENAI_API_KEY` | `sk-prod-...` | `sk-prod-...` | `sk-prod-...` |
| `PINECONE_API_KEY` | `pcsk_...` | `pcsk_...` | `pcsk_...` |
| `PINECONE_HOST` | Index host URL | Same | Same |
| `PINECONE_NAMESPACE_PREFIX` | `""` | `"staging-"` | `"dev-"` |
| `API_SECRET_KEY` | Strong random | Different | Different |
| `SMTP_PASSWORD` | Gmail app pwd | `""` (disabled) | `""` (disabled) |
| `ESEWA_SECRET_KEY` | Live key | Sandbox key | Sandbox key |
| `KHALTI_SECRET_KEY` | Live key | Sandbox key | Sandbox key |
| `ENVIRONMENT` | `production` | `staging` | `dev` |

---

## 6. Migration Strategy

### Migration Runner (`scripts/migrate.py`)

Lightweight migration runner that tracks applied migrations via a `_migrations` table.

**How it works:**
1. Connects to target database (from `DATABASE_URL` env var)
2. Creates `_migrations` tracking table if not exists
3. Scans `backend/migrations/*.sql`, sorted alphabetically
4. Compares against `_migrations` to find unapplied migrations
5. Applies each in a transaction, records filename + SHA-256 checksum
6. Aborts on first failure, reports which migration failed

**Tracking table:**
```sql
CREATE TABLE IF NOT EXISTS _migrations (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) UNIQUE NOT NULL,
    applied_at TIMESTAMP DEFAULT NOW(),
    checksum VARCHAR(64) NOT NULL
);
```

### Migration Safety Rules

1. **Forward-only**: No down migrations. Write corrective migrations for rollbacks.
2. **Idempotent**: Every migration must use `IF NOT EXISTS` / `IF EXISTS` guards.
3. **Promotion order**: Always apply to dev first, then staging, then production.
4. **Destructive ops**: `DROP TABLE`, `DROP COLUMN` require manual approval (run via `migrate.yml` workflow_dispatch).
5. **Testing**: A migration must run successfully on dev and staging before reaching production.

### Migration File Naming

```
NNN_description.sql

Examples:
001_add_content_column.sql
002_add_quick_actions.sql
...
024_add_new_feature.sql
```

Sequential numbering. Unique numbers only (no duplicates).

---

## 7. Deploy Script (`scripts/deploy.sh`)

VPS-side script called by GitHub Actions via SSH.

```
Usage:
  deploy.sh <env>              # Deploy latest image
  deploy.sh <env> --rollback   # Rollback to previous image

Environments: prod, staging, dev

Deploy flow:
  1. Tag current running image as {env}-previous
  2. Pull new {env}-latest image from GHCR
  3. Run pending database migrations
  4. Restart container via docker compose --profile {env}
  5. Wait for health check (30s)

Rollback flow:
  1. Swap {env}-previous back to {env}-latest
  2. Restart container
  3. Skip migrations (DB changes are forward-only)
```

---

## 8. Rollback Strategy

| Component | Rollback Method | Time to Recovery |
|-----------|----------------|-----------------|
| **Backend** | `deploy.sh {env} --rollback` swaps to previous Docker image | ~30 seconds |
| **Widget/Admin** | Vercel dashboard > Promote previous deployment | ~10 seconds |
| **Database** | Write corrective migration. Emergency: Supabase SQL editor | ~5-15 minutes |
| **Git** | Revert merge commit, push to trigger redeploy | ~2-3 minutes |

**Automatic rollback**: The deploy workflow runs a health check after deployment. If `/health` returns non-200 for 60 seconds, it automatically triggers rollback.

---

## 9. Environment Variables

### Full Variable Reference (`backend/.env.example`)

```bash
# ── Environment ──────────────────────────────────
ENVIRONMENT=production          # production | staging | dev

# ── OpenAI ───────────────────────────────────────
OPENAI_API_KEY=sk-...

# ── Pinecone ─────────────────────────────────────
PINECONE_API_KEY=pcsk_...
PINECONE_HOST=https://...svc.pinecone.io
PINECONE_INDEX_NAME=zunkiree-search
PINECONE_NAMESPACE_PREFIX=      # "" for prod, "staging-" for staging, "dev-" for dev

# ── Database (Supabase PostgreSQL) ───────────────
DATABASE_URL=postgresql://user:pass@host:5432/db?options=-c search_path=public

# ── Application ──────────────────────────────────
API_SECRET_KEY=change-this-in-production
ALLOWED_ORIGINS=https://zunkiree-admin.vercel.app,https://zunkiree-search-v1.vercel.app

# ── LLM Configuration ───────────────────────────
LLM_MODEL=gpt-4o-mini
LLM_MODEL_PREMIUM=gpt-4o
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=500

# ── Embeddings ───────────────────────────────────
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSIONS=3072

# ── SMTP (Email Verification) ───────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=

# ── Payment Gateways ────────────────────────────
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
ESEWA_MERCHANT_CODE=
ESEWA_SECRET_KEY=
ESEWA_SANDBOX=true
KHALTI_SECRET_KEY=
KHALTI_SANDBOX=true
```

---

## 10. CODEOWNERS

Critical paths that require review before merging:

```
# Deployment & infrastructure
docker-compose.yml          @zunkireelabs/leads
.github/                    @zunkireelabs/leads
scripts/                    @zunkireelabs/leads

# Database migrations
backend/migrations/         @zunkireelabs/leads

# Security-sensitive config
backend/app/config.py       @zunkireelabs/leads
```

---

## 11. Implementation Checklist

### Code Changes (automated via CI/CD setup)
- [ ] Fix duplicate migration numbering (020, 021 duplicates)
- [ ] Create `scripts/migrate.py` migration runner
- [ ] Add `ENVIRONMENT` and `PINECONE_NAMESPACE_PREFIX` to `backend/app/config.py`
- [ ] Update `backend/app/services/vector_store.py` for namespace prefix
- [ ] Rewrite `docker-compose.yml` for multi-environment
- [ ] Create `scripts/deploy.sh` VPS deploy script
- [ ] Create `.github/workflows/ci.yml`
- [ ] Create `.github/workflows/deploy-backend.yml`
- [ ] Create `.github/workflows/migrate.yml`
- [ ] Create `backend/.env.example`
- [ ] Create `.github/CODEOWNERS`
- [ ] Fix hardcoded `API_URL` in `admin/index.html` and `admin/dashboard.html`
- [ ] Update `.gitignore` (add `envs/*.env`)
- [ ] Enhance `backend/Dockerfile` with multi-stage build

### Manual Setup (requires UI/CLI access)
- [ ] Create `develop` and `staging` branches from `main`
- [ ] Set up GitHub Environments (`production`, `staging`, `development`)
- [ ] Add GitHub Secrets (repository-level and per-environment)
- [ ] Configure GitHub branch protection rules
- [ ] Create Supabase schemas (`staging`, `dev`) via SQL editor
- [ ] Add DNS A records for `api-staging` and `api-dev` subdomains
- [ ] Set up VPS directory structure (`/opt/zunkiree/envs/`)
- [ ] Create env files on VPS (`prod.env`, `staging.env`, `dev.env`)

### Verification
- [ ] CI runs on PR to `develop`
- [ ] Merge to `develop` auto-deploys to `api-dev.zunkireelabs.com`
- [ ] Merge to `staging` auto-deploys to `api-staging.zunkireelabs.com`
- [ ] Merge to `main` auto-deploys to `api.zunkireelabs.com`
- [ ] Health check passes on all environments
- [ ] Rollback works when health check fails
- [ ] Migrations run correctly per environment
- [ ] Branch protection blocks direct push to `main`

---

## 12. Cost Analysis

| Item | Monthly Cost | Notes |
|------|-------------|-------|
| VPS (existing) | $0 extra | 3 containers on same VPS; staging/dev resource-limited |
| Vercel (existing) | $0 | Preview deployments free on all plans |
| GitHub Actions | $0 | 2000 free minutes/month (private), unlimited (public) |
| GHCR | $0 | 500MB free; Docker images ~150MB each |
| Supabase (existing) | $0 extra | Schema isolation on same project |
| Pinecone (existing) | $0 extra | Namespace prefixes on same index |
| DNS records | $0 | Two subdomains on existing domain |
| **Total** | **$0** | |
