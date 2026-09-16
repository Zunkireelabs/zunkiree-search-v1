from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# Supavisor's session-mode pooler (port 5432) enforces a client ceiling of 15
# for the whole Supabase project — shared by stage AND prod. SQLAlchemy's
# unconfigured defaults (pool_size=5, max_overflow=10 => 15) let a single
# environment alone consume the entire shared ceiling.
#
# This budget is process-wide, not worker-wide: uvicorn runs multiple worker
# processes, each with its own engine/pool, so worker_count multiplies these
# numbers. Sizing must be divided by the worker count actually in use —
# see Dockerfile:18 (prod --workers) / docker-compose.yml:91 (stage
# --workers). `uvicorn_workers` lets a deploy declare its own worker count;
# unset, we fall back to the currently-documented counts (prod=2, staging=1).
# If either --workers flag changes, this must be re-derived — either set
# UVICORN_WORKERS to match, or update the fallback below.
#
# Total socket budget per environment (pool_size + max_overflow, summed
# across all workers), leaving headroom for psql, migrations, the background
# dispatcher, and the Supabase dashboard against the shared 15-connection
# ceiling:
#   prod:    8  (currently 2 workers x (pool_size=2 + max_overflow=2))
#   staging: 2  (currently 1 worker  x (pool_size=1 + max_overflow=1))
#   total:   10 of 15 -> 5 connections of headroom
#
# Default to the SMALL (staging-sized) budget for anything that isn't
# explicitly "production" — including local dev and an unset/unrecognized
# environment value. config.py:8 defaults an unset ENVIRONMENT to
# "production", so a laptop running the backend locally against the shared
# pool MUST set ENVIRONMENT=development in its .env, or it silently takes
# the full production-sized (8-socket) budget. Failing large used to be the
# safe default when the ceiling had ~14-of-15 headroom; at 10-of-15 an
# unrecognized environment taking the big budget is itself capable of
# recreating the incident this PR fixes (a local dev backend contributed to
# it). Fail small instead.
_worker_count = settings.uvicorn_workers or (2 if settings.environment == "production" else 1)
_total_socket_budget = 8 if settings.environment == "production" else 2
_per_worker_budget = max(1, _total_socket_budget // _worker_count)
_default_pool_size = max(1, _per_worker_budget // 2)
_default_max_overflow = _per_worker_budget - _default_pool_size
# NOTE: max(1, ...) means each worker always gets at least 1+1 sockets, so
# the total budget stops being enforced if worker_count exceeds the budget
# (e.g. 16 workers => 16 sockets against an 8-socket budget). Fine at
# today's worker counts (2 prod / 1 staging); revisit if workers scale up.

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size if settings.db_pool_size is not None else _default_pool_size,
    max_overflow=settings.db_max_overflow if settings.db_max_overflow is not None else _default_max_overflow,
    pool_timeout=10,  # fail fast with a clean error instead of hanging the request
    connect_args={"statement_cache_size": 0},  # Required for Supabase Supavisor pooler
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
