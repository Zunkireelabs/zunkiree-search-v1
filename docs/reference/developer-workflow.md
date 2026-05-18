# Developer Workflow

## Flow Diagram

```
DEVELOPER'S MACHINE (Local)
════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────┐
  │  1. Clone repo (first time)     │
  │  git clone <repo-url>           │
  │  cp backend/.env.example        │
  │     backend/.env                │
  │  (fill in shared dev keys)      │
  └───────────────┬─────────────────┘
                  │
                  ▼
  ┌─────────────────────────────────┐
  │  2. Create feature branch       │
  │  git checkout -b feature/xyz    │
  └───────────────┬─────────────────┘
                  │
                  ▼
  ┌─────────────────────────────────┐
  │  3. Run locally & develop       │
  │                                 │
  │  Terminal 1:                    │
  │  docker compose --profile dev up│
  │  → Backend at localhost:8000    │
  │                                 │
  │  Terminal 2:                    │
  │  cd widget && npm run dev       │
  │  → Widget at localhost:5173     │
  │                                 │
  │  Test via browser/curl/Postman  │
  └───────────────┬─────────────────┘
                  │
                  ▼
  ┌─────────────────────────────────┐
  │  4. Commit & push               │
  │  git add .                      │
  │  git commit -m "Add xyz"        │
  │  git push origin feature/xyz    │
  └───────────────┬─────────────────┘
                  │
                  │
GITHUB            ▼
════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────┐
  │  5. Open Pull Request           │
  │  feature/xyz → main             │
  │  Write description of changes   │
  └───────────────┬─────────────────┘
                  │
                  ▼
  ┌─────────────────────────────────────────────────┐
  │  6. CI runs automatically (GitHub Actions)      │
  │                                                 │
  │  ┌──────────────┐    ┌──────────────┐           │
  │  │ backend-check│    │ widget-check │  parallel │
  │  │              │    │              │           │
  │  │ - ruff lint  │    │ - tsc check  │           │
  │  │ - py_compile │    │ - npm build  │           │
  │  │ - imports    │    │              │           │
  │  │ - .env check │    │              │           │
  │  └──────┬───────┘    └──────┬───────┘           │
  │         │                   │                   │
  │         └─────────┬─────────┘                   │
  │                   ▼                             │
  │         ┌──────────────┐                        │
  │         │ docker-build │                        │
  │         └──────┬───────┘                        │
  │                │                                │
  │                ▼                                │
  │       PASSED (green)    OR    FAILED (red)      │
  └─────────┬───────────────────────┬───────────────┘
            │                       │
            │                       ▼
            │            ┌─────────────────────┐
            │            │ BLOCKED             │
            │            │ Merge button grey   │
            │            │ Dev fixes code,     │
            │            │ pushes again,       │
            │            │ CI re-runs          │
            │            └─────────────────────┘
            │
            ▼
  ┌─────────────────────────────────────────────────┐
  │  7. NEED TO TEST CHATBOT/PAYMENTS?              │
  │     (features that need public URL)             │
  │                                                 │
  │  YES:                                           │
  │  Go to Actions → "Deploy to Staging"            │
  │  → Pick your branch (feature/xyz)               │
  │  → Click "Run workflow"                         │
  │  → Deploys to staging-api.zunkireelabs.com      │
  │  → Test Instagram DMs, payment callbacks there  │
  │                                                 │
  │  NO: Skip this step                             │
  └───────────────┬─────────────────────────────────┘
                  │
                  ▼
  ┌─────────────────────────────────┐
  │  8. Merge PR                    │
  │  CI passed                      │
  │  Click "Squash and merge"       │
  │  feature/xyz → main             │
  │  Branch auto-deleted            │
  └───────────────┬─────────────────┘
                  │
                  │
VPS (PRODUCTION)  ▼
════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────────────────────┐
  │  9. Auto-deploy triggers (GitHub Actions)       │
  │                                                 │
  │  SSH into VPS                                   │
  │    │                                            │
  │    ├── git pull origin main                     │
  │    │                                            │
  │    ├── Run migrations (if new .sql files)       │
  │    │   ./scripts/migrate.sh                     │
  │    │                                            │
  │    ├── docker compose build                     │
  │    │   zunkiree-search-api                      │
  │    │                                            │
  │    ├── docker compose up -d --force-recreate    │
  │    │   zunkiree-search-api                      │
  │    │                                            │
  │    └── Health check (3 retries)                 │
  │        curl /health                             │
  │                                                 │
  │  LIVE at api.zunkireelabs.com                   │
  └───────────────┬─────────────────────────────────┘
                  │
                  │
VERCEL (WIDGET)   │  (happens in parallel, separate pipeline)
════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────┐
  │  10. Vercel auto-deploys widget │
  │  (only if widget/ files changed)│
  │                                 │
  │  npm run build → CDN update     │
  │  LIVE on client websites        │
  └─────────────────────────────────┘


════════════════════════════════════════════════════════════════
IF SOMETHING BREAKS AFTER DEPLOY
════════════════════════════════════════════════════════════════

  Option A (easiest):
  ┌─────────────────────────────────┐
  │  GitHub → merged PR → "Revert"  │
  │  → Creates revert PR            │
  │  → Merge it                     │
  │  → Auto-deploy fixes production │
  └─────────────────────────────────┘

  Option B (emergency, ~30 seconds):
  ┌─────────────────────────────────┐
  │  ssh anish@94.136.189.213       │
  │  cd zunkiree-search-v1          │
  │  git revert HEAD --no-edit      │
  │  docker compose build ...       │
  │  docker compose up -d ...       │
  │  → Production rolled back       │
  └─────────────────────────────────┘
```

---

## Step-by-Step Guide

### First Time Setup

```bash
git clone https://github.com/Zunkireelabs/zunkiree-search-v1.git
cd zunkiree-search-v1
cp backend/.env.example backend/.env   # fill in shared dev keys from team lead
cd widget && npm install && cd ..
```

### Daily Development

```bash
# 1. Create feature branch
git checkout -b feature/your-feature

# 2. Run backend (Terminal 1)
docker compose --profile dev up

# 3. Run widget (Terminal 2)
cd widget && npm run dev

# 4. Make changes, test at localhost:8000 and localhost:5173

# 5. Push when ready
git add .
git commit -m "Add your feature"
git push origin feature/your-feature
```

### Getting to Production

1. **Open PR** on GitHub — `feature/your-feature` → `main`
2. **CI runs automatically** — wait for green checks
3. **Testing chatbot/payments?** → Go to Actions → "Deploy to Staging" → pick your branch
4. **Merge** — click "Squash and merge"
5. **Auto-deploy** — VPS updates within ~2 minutes
6. **Widget** — Vercel auto-deploys if widget files changed

### Rollback (If Something Breaks)

| Method | When to use | How |
|--------|-------------|-----|
| GitHub Revert | Normal rollback | Go to merged PR → click "Revert" → merge the revert PR → auto-deploys |
| Emergency SSH | Production is down | `ssh anish@94.136.189.213` → `git revert HEAD --no-edit` → rebuild → restart |

---

## What Gets Tested Where

| Feature | Local (localhost) | Staging (staging-api) | Production (api) |
|---------|-------------------|----------------------|------------------|
| Widget UI | `npm run dev` | — | Vercel CDN |
| Backend API / RAG | `docker compose --profile dev up` | Deploy branch | Auto on merge |
| Ecommerce (cart, orders) | localhost:8000 | staging-api | Auto on merge |
| Chatbot (Meta webhooks) | Simulate POST to localhost | Real Instagram DMs | Auto on merge |
| Payment callbacks | Sandbox + simulate | Sandbox + real callbacks | Live payments |

---

## Branch Naming

| Prefix | Use for |
|--------|---------|
| `feature/` | New features |
| `fix/` | Bug fixes |
| `chore/` | Refactoring, deps, CI |
| `docs/` | Documentation |
