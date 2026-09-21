"""Known issue (xfail): a client disconnect that cancels /query/stream mid-DB-call
orphans an asyncpg backend that keeps running its query until the garbage
collector finds it (~0.4s in prod). Pool bookkeeping LIES here —
pool.checkedout() is 0 — so this asserts against the SERVER's view instead.
Mechanism, rejected fixes and the decision: docs/reference/db-cancellation-leak.md

Strict xfail: the day someone fixes the leak this XPASSes and fails the suite,
forcing them to delete the marker.

Needs a real Postgres, so it is skipped unless TEST_DATABASE_URL is set (CI
does not set it). Local recipe:
    docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=pw -p 55432:5432 postgres:16-alpine
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:pw@localhost:55432/postgres \\
        .venv311/bin/python -m pytest tests/test_db_cancel_release.py -v
    docker rm -f pgtest
It drives the real app.database.get_db + CorrelationMiddleware with a raw ASGI
http.disconnect during `select pg_sleep(30)`. The leak shows up around the 3rd
cancel cycle, so it loops 5 times. GC is disabled so nothing masks it.
"""
import asyncio
import gc
import os

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.database as database
from app.middleware.correlation import CorrelationMiddleware

TEST_DB = os.environ.get("TEST_DATABASE_URL")
APP_NAME = "cancel-release-test"
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set (needs real Postgres)")


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationMiddleware)

    @app.post("/stream")
    async def stream(db: AsyncSession = Depends(database.get_db)):
        async def gen():
            await db.execute(text("select pg_sleep(30)"))  # in flight when cancelled
            yield b"data: x\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


async def _call_then_disconnect(app, disconnect_after: float):
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "path": "/stream", "raw_path": b"/stream", "query_string": b"", "headers": [],
        "client": ("127.0.0.1", 1), "server": ("test", 80), "scheme": "http",
    }
    sent_body = False

    async def receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(disconnect_after)
        return {"type": "http.disconnect"}

    async def send(message):
        pass

    try:
        await asyncio.wait_for(app(scope, receive, send), timeout=15)
    except (asyncio.CancelledError, Exception):
        pass  # client is gone; what matters is what the server looks like afterwards


@pytest.mark.xfail(
    strict=True,
    reason="Known: disconnect mid-query orphans a backend until GC — see docs/reference/db-cancellation-leak.md",
)
@pytest.mark.asyncio
async def test_cancel_mid_execute_leaves_no_orphaned_backend(monkeypatch):
    engine = create_async_engine(
        TEST_DB, pool_size=1, max_overflow=0, pool_timeout=5,
        connect_args={"server_settings": {"application_name": APP_NAME}},
    )
    observer = create_async_engine(TEST_DB, poolclass=NullPool)
    monkeypatch.setattr(
        database, "async_session_maker",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    gc.disable()
    try:
        for _ in range(5):
            await _call_then_disconnect(_build_app(), disconnect_after=0.5)
            assert engine.pool.checkedout() == 0  # passes even while leaking
            async with observer.connect() as conn:
                open_backends = (await conn.execute(text(
                    "select count(*) from pg_stat_activity where application_name = :n"
                ), {"n": APP_NAME})).scalar_one()
            tracked = engine.pool.checkedin() + engine.pool.checkedout()
            assert open_backends <= tracked, f"{open_backends} backends vs {tracked} tracked"
    finally:
        gc.enable()
        async with observer.connect() as conn:  # don't leave pg_sleep(30) running
            await conn.execute(text(
                "select pg_terminate_backend(pid) from pg_stat_activity where application_name = :n"
            ), {"n": APP_NAME})
        await observer.dispose()
        await engine.dispose()
