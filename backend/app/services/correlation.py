"""
Correlation ID context (per SHARED-CONTRACT.md §5).

A request-scoped UUID v4 that traces one logical operation across both systems'
logs and outbound calls. The middleware (`app.middleware.correlation`) sets this
on every incoming request; the connector reads it and stamps every outbound
httpx call with `X-Correlation-Id`.

contextvars are local to the asyncio task. FastAPI runs each request in its own
task, so the value set at request entry is visible to all `await`ed code in that
handler. Background tasks (`asyncio.create_task`) do not inherit contextvars
automatically — capture the value in the parent and re-set it in the child if
fan-out is ever introduced.
"""
import uuid
from contextvars import ContextVar
from typing import Optional

_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str:
    """Return the current correlation ID, generating one if none is set.

    Generation-on-read keeps connector code simple: outbound calls outside a
    request scope (e.g., scheduled jobs in the future) still get a valid ID.
    """
    current = _correlation_id.get()
    if current is None:
        current = str(uuid.uuid4())
        _correlation_id.set(current)
    return current


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)
