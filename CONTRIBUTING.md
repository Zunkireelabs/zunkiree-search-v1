# Contributing to Zunkiree Search

## Prerequisites

- **Docker + Docker Compose** (for backend)
- **Node.js 18+** (for widget)
- **Python 3.11+** (optional, for running backend without Docker)

## Quick Start

### 1. Clone & Configure

```bash
git clone https://github.com/Zunkireelabs/zunkiree-search-v1.git
cd zunkiree-search-v1
cp backend/.env.example backend/.env
```

Fill in `backend/.env` with shared dev keys (get from team lead):
- `DATABASE_URL` — shared Supabase dev project
- `OPENAI_API_KEY` — shared team key
- `PINECONE_API_KEY` + `PINECONE_HOST`
- `API_SECRET_KEY` — any string for local dev

Leave Meta/Payment keys blank unless working on chatbot or payments.

### 2. Run Backend (Docker — recommended)

```bash
docker compose --profile dev up
```

Backend running at **http://localhost:8000**. Test: `curl http://localhost:8000/health`

Hot reload is enabled — edit files in `backend/` and the server restarts automatically.

### 3. Run Backend (without Docker)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Run Widget

```bash
cd widget
npm install
npm run dev
```

Widget dev server at **http://localhost:5173**.

## Development Workflow

See [docs/developer-workflow.md](docs/developer-workflow.md) for the full flow diagram.

### Short version:

```bash
# 1. Create feature branch
git checkout -b feature/your-feature

# 2. Develop & test locally
docker compose --profile dev up    # Terminal 1
cd widget && npm run dev           # Terminal 2

# 3. Push
git add . && git commit -m "Add feature" && git push origin feature/your-feature

# 4. Open PR on GitHub → CI runs → merge when green
```

## Branch Naming

| Prefix | Use for |
|--------|---------|
| `feature/` | New features |
| `fix/` | Bug fixes |
| `chore/` | Refactoring, deps, CI |
| `docs/` | Documentation |

## Testing Chatbot / Payments

These features need a public URL (Meta webhooks, payment callbacks don't reach localhost).

1. Push your branch to GitHub
2. Go to **Actions → "Deploy to Staging"**
3. Enter your branch name → Run workflow
4. Test at `staging-api.zunkireelabs.com`

## Running Linter Locally

```bash
pip install ruff
cd backend && ruff check app/
```

## Local Database (Optional)

For fully isolated local dev without shared Supabase:

```bash
docker run -d --name zunkiree-pg -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:16-alpine
# Set DATABASE_URL=postgresql://postgres:dev@localhost:5432/postgres in .env
./scripts/migrate.sh
```
