from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# Supavisor's session-mode pooler (port 5432) enforces a client ceiling of 15
# for the whole Supabase project — shared by stage AND prod. SQLAlchemy's
# unconfigured defaults (pool_size=5, max_overflow=10 => 15) let a single
# environment alone consume the entire shared ceiling. Keep each environment's
# max well below 15, with staging smaller than prod so stage traffic can never
# starve prod. See CLAUDE.md / [[zunkiree_environment_topology]].
_default_pool_size = 2 if settings.environment == "staging" else 4
_default_max_overflow = 2 if settings.environment == "staging" else 3

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
