import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from app.middleware.correlation import CorrelationMiddleware
from app.services.inbound_event_dispatcher import run_dispatcher_loop

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
    # against the shared Supabase (locked Z4 §1.5).
    stop_event = asyncio.Event()
    dispatcher_task = asyncio.create_task(run_dispatcher_loop(stop_event))
    app.state.inbound_dispatcher_stop_event = stop_event
    app.state.inbound_dispatcher_task = dispatcher_task

    yield

    # Shutdown
    print("Shutting down Zunkiree Search API...")
    stop_event.set()
    try:
        await asyncio.wait_for(dispatcher_task, timeout=10)
    except asyncio.TimeoutError:
        dispatcher_task.cancel()
        try:
            await dispatcher_task
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


@app.get("/")
async def root():
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
