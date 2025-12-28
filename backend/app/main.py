from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.api import query_router, widget_router, admin_router

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
    yield
    # Shutdown
    print("Shutting down Zunkiree Search API...")


app = FastAPI(
    title="Zunkiree Search API",
    description="AI-powered search widget backend",
    version="1.0.0",
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

# Include routers
app.include_router(query_router, prefix="/api/v1")
app.include_router(widget_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


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
