"""
Correlation ID middleware (per SHARED-CONTRACT.md §5).

Reads `X-Correlation-Id` from the request; if absent, generates a UUID v4. Sets
the contextvar so downstream handlers + outbound httpx calls share it. Echoes
the value back on the response per §5.3.

Registration order in `main.py` matters: register AFTER CORSMiddleware so this
middleware is the OUTERMOST layer (FastAPI/Starlette applies middleware in
reverse registration order; the last-registered runs first on the request). The
contextvar is set before any other middleware or handler runs.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.correlation import set_correlation_id

HEADER_NAME = "X-Correlation-Id"


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(HEADER_NAME)
        correlation_id = incoming if incoming else str(uuid.uuid4())
        set_correlation_id(correlation_id)
        response = await call_next(request)
        response.headers[HEADER_NAME] = correlation_id
        return response
