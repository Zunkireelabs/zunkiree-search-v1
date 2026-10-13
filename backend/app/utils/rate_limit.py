"""A small in-process rolling-window limiter for the education endpoints.

Every education message can cost an AI call, so one visitor address is capped per tenant. The counters live in this
worker's memory: production runs two uvicorn workers that count separately (the real ceiling is up to twice the number
here) and a restart clears them. That is enough to stop a script from running up the bill; it is not a billing guard.
"""
import math
import time
from collections import deque

from fastapi import HTTPException

CHAT_LIMIT = 20       # education messages per visitor address per window
HISTORY_LIMIT = 60    # page-reload history reads (no AI call, so looser)
WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits: dict[str, deque] = {}

    def hit(self, key: str, limit: int, window: int) -> int | None:
        """Count one request. None = allowed; otherwise the seconds to wait. Refused requests are not counted."""
        now = self._clock()
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= window]:
            del self._hits[k]                       # idle visitors, so memory does not grow
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= limit:
            return max(1, math.ceil(window - (now - q[0])))
        q.append(now)
        return None


_limiter = RateLimiter()


def reset_rate_limits() -> None:
    _limiter._hits.clear()


def client_ip(request) -> str:
    """The visitor address. Behind the proxy the last X-Forwarded-For entry is the one the proxy itself added; the first
    entries are written by the client and could be invented to dodge the limit."""
    fwd = request.headers.get("x-forwarded-for", "") if request is not None else ""
    last = fwd.split(",")[-1].strip()
    if last:
        return last
    client = getattr(request, "client", None)
    return client.host if client else "unknown"


def enforce(request, site_id: str, scope: str, limit: int) -> None:
    wait = _limiter.hit(f"{scope}:{site_id}:{client_ip(request)}", limit, WINDOW_SECONDS)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail={"code": "RATE_LIMITED", "message": "Too many messages. Please wait a moment and try again."},
            headers={"Retry-After": str(wait)},
        )
