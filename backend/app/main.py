import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.database import init_db
from app.api import query_router, widget_router, admin_router, dashboard_router
from app.api.cart import router as cart_router
from app.api.orders import router as orders_router
from app.api.webhooks import router as webhooks_router
from app.api.ecommerce_dashboard import router as ecommerce_dashboard_router
from app.api.payments import router as payments_router
from app.api.chatbot_webhooks import router as chatbot_webhooks_router
from app.api.chatbot_admin import router as chatbot_admin_router
from app.api.admin_backend_credentials import router as admin_backend_credentials_router
from app.api.hooks_stella import router as hooks_stella_router
from app.api.admin_inbound_webhooks import router as admin_inbound_webhooks_router
from app.api.admin_tenants import router as admin_tenants_router
from app.middleware.correlation import CorrelationMiddleware
from app.services.inbound_event_dispatcher import run_dispatcher_loop
from app.services.clinic_prewarm import run_clinic_prewarm_loop

# --- Logging configuration (before anything else) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
# Silence noisy third-party libraries
for _lib in ("httpx", "httpcore", "openai", "pinecone", "pinecone_plugin_interface"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting Zunkiree Search API...")
    try:
        await init_db()
        print("Database initialized.")
    except Exception as e:
        print(f"Warning: Database initialization failed: {e}")
        print("App will continue without database init - tables may already exist.")

    # Z4 inbound webhook dispatcher — single asyncio task per container.
    # Both stage and prod replicas run it; SELECT ... FOR UPDATE SKIP LOCKED
    # in the dispatcher's batch picker prevents duplicate row processing
    # against the shared Supabase (locked Z4 §1.5). ENABLE_INBOUND_DISPATCHER
    # defaults true so every existing container is unchanged; the P2 clinic
    # lane sets it false — one lane, one job (see config.py, P2 brief §4 B2).
    stop_event = asyncio.Event()
    dispatcher_task: asyncio.Task | None = None
    if settings.enable_inbound_dispatcher:
        dispatcher_task = asyncio.create_task(run_dispatcher_loop(stop_event))
    app.state.inbound_dispatcher_stop_event = stop_event
    app.state.inbound_dispatcher_task = dispatcher_task

    # P4 B2: clinic lane cold-start tax. Same fire-and-forget pattern as the
    # dispatcher above, own stop_event so it shuts down independently.
    clinic_prewarm_stop_event = asyncio.Event()
    clinic_prewarm_task: asyncio.Task | None = None
    if settings.enable_clinic_prewarm:
        clinic_prewarm_task = asyncio.create_task(run_clinic_prewarm_loop(clinic_prewarm_stop_event))
    app.state.clinic_prewarm_stop_event = clinic_prewarm_stop_event
    app.state.clinic_prewarm_task = clinic_prewarm_task

    yield

    # Shutdown
    print("Shutting down Zunkiree Search API...")
    stop_event.set()
    clinic_prewarm_stop_event.set()
    if dispatcher_task is not None:
        try:
            await asyncio.wait_for(dispatcher_task, timeout=10)
        except asyncio.TimeoutError:
            dispatcher_task.cancel()
            try:
                await dispatcher_task
            except (asyncio.CancelledError, Exception):
                pass
    if clinic_prewarm_task is not None:
        try:
            await asyncio.wait_for(clinic_prewarm_task, timeout=10)
        except asyncio.TimeoutError:
            clinic_prewarm_task.cancel()
            try:
                await clinic_prewarm_task
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(
    title="Zunkiree Search API",
    description="AI-powered search widget backend",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS middleware
allowed_origins = [origin.strip() for origin in settings.allowed_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registered AFTER CORS so it's the outermost layer (Starlette applies
# middleware in reverse registration order; last-registered runs first on
# the request). Sets the correlation contextvar before any handler runs so
# downstream connector calls and logs can read it.
app.add_middleware(CorrelationMiddleware)

# Include routers
app.include_router(query_router, prefix="/api/v1")
app.include_router(widget_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(cart_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(ecommerce_dashboard_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(chatbot_webhooks_router, prefix="/api/v1")
app.include_router(chatbot_admin_router, prefix="/api/v1")
app.include_router(admin_backend_credentials_router, prefix="/api/v1")
app.include_router(hooks_stella_router, prefix="/api/v1")
app.include_router(admin_inbound_webhooks_router, prefix="/api/v1")
app.include_router(admin_tenants_router, prefix="/api/v1")


# HR Goel demo (2026-09-30) — hr-goel.zunkireelabs.com DNS points at this
# same VPS (see docker-compose.yml's zunkiree-hrgoel-demo Traefik router).
# Serving the demo page by Host header here avoids standing up a separate
# static site just for one demo; API routes under /api/v1 are unaffected
# since FastAPI dispatches by path, not Host. Direct-to-Zunkiree for the
# demo, not through Orca — see HR-GOEL-AGENT-BRIEF.md (brain folder).
HR_GOEL_DEMO_HOST = "hr-goel.zunkireelabs.com"
HR_GOEL_DEMO_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HR Goel Group</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 3rem 1.5rem; background: #f7f7f8; color: #1a1a1a; }
  .wrap { max-width: 640px; margin: 0 auto; }
  h1 { font-size: 1.75rem; margin-bottom: 0.25rem; }
  p { color: #444; line-height: 1.5; }
</style>
</head>
<body>
  <div class="wrap">
    <h1>HR Goel Group</h1>
    <p>Ask our assistant about our bitumen, cement, construction chemicals, hydropower, and auto product lines &mdash; or request a quote.</p>
  </div>
  <script
    src="https://zunkiree-search-v1.vercel.app/zunkiree-widget.iife.js"
    data-site-id="hr-goel"
    data-api-url="https://staging-api.zunkireelabs.com"
    data-mode="agent"
    async
  ></script>
</body>
</html>
"""


@app.get("/")
async def root(request: Request):
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host == HR_GOEL_DEMO_HOST:
        return HTMLResponse(HR_GOEL_DEMO_HTML)
    return {
        "name": "Zunkiree Search API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
    }
