"""
Correlation middleware tests.

Verifies SHARED-CONTRACT.md §5: the middleware reads X-Correlation-Id from the
incoming request (or generates one), sets the contextvar so handlers and
outbound connector calls share it, and echoes the value back on the response.
"""
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.correlation import CorrelationMiddleware, HEADER_NAME
from app.services.correlation import get_correlation_id


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationMiddleware)

    @app.get("/probe")
    def probe():
        # Reading the contextvar inside the handler proves the middleware set
        # it before the handler ran. The response body carries the value back
        # for the test to assert against the response header.
        return {"correlation_id": get_correlation_id()}

    return app


def test_middleware_uses_incoming_header_value():
    client = TestClient(_build_app())
    incoming = "12345678-1234-1234-1234-123456789012"
    resp = client.get("/probe", headers={HEADER_NAME: incoming})

    assert resp.status_code == 200
    assert resp.headers[HEADER_NAME] == incoming
    assert resp.json()["correlation_id"] == incoming


def test_middleware_generates_uuid_when_header_absent():
    client = TestClient(_build_app())
    resp = client.get("/probe")

    assert resp.status_code == 200
    assert HEADER_NAME in resp.headers
    cid = resp.headers[HEADER_NAME]
    assert len(cid) == 36
    uuid.UUID(cid)
    # Handler observed the same value the middleware set.
    assert resp.json()["correlation_id"] == cid


def test_middleware_per_request_isolation():
    """Two requests, two distinct generated correlation IDs. Confirms the
    contextvar is per-request and not leaking across calls."""
    client = TestClient(_build_app())
    a = client.get("/probe").headers[HEADER_NAME]
    b = client.get("/probe").headers[HEADER_NAME]
    assert a != b
