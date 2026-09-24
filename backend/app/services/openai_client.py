"""
Single constructor for every AsyncOpenAI client in the app.

Every call site used to build `AsyncOpenAI(api_key=...)` with no `timeout`
or `max_retries`, which leaves the SDK defaults in place: ~600s timeout,
2 retries. A stalled OpenAI call under those defaults can hang a request
for up to ~10 minutes with no error surfaced to the client — and, on the
default-RAG path, pins a DB pooler connection idle-in-transaction for the
same span (see P2 brief §7c B4; reproduced on stage 2026-09-24).

Two bounded profiles, chosen so a voice turn fails cleanly inside Orca's
25s run timeout instead of hanging past it:

- "embeddings": text-embedding-3-large calls in the hot RAG retrieval
  path. 8s timeout, 1 retry (~16s worst case for the single call). This
  is normally the very first external call in a turn, so 16s still
  leaves headroom under the 25s budget.
- "chat" (default): every chat/completions call — the standalone RAG
  answer, the ecommerce/hospitality/clinic agent tool-loop calls, the
  rerank and classifier calls. 15s timeout, 0 retries, so no single call
  can ever exceed ~15s. Multi-tool agent turns chain several of these
  calls; capping each one individually (rather than doubling any of them
  via a retry) keeps the turn's own iteration/turn-level timeout the
  thing that bounds total turn duration, not a single retried call.

Both profiles fail with `openai.APITimeoutError` (a subclass of
`openai.APIConnectionError`) once the bound is hit, which every call site
already lets propagate up to its own exception handling (e.g. the
default-RAG stream's outer `except Exception` in `api/query.py`, which
turns it into a clean SSE `error` event).
"""
from openai import AsyncOpenAI

from app.config import get_settings

EMBEDDING_TIMEOUT_SECONDS = 8.0
EMBEDDING_MAX_RETRIES = 1
CHAT_TIMEOUT_SECONDS = 15.0
CHAT_MAX_RETRIES = 0


def get_openai_client(kind: str = "chat", api_key: str | None = None) -> AsyncOpenAI:
    """Build a bounded AsyncOpenAI client.

    Args:
        kind: "embeddings" or "chat" (default). Picks the timeout/retry profile.
        api_key: Overrides `settings.openai_api_key` (e.g. a per-tenant key).
    """
    settings = get_settings()
    key = api_key or settings.openai_api_key
    if kind == "embeddings":
        return AsyncOpenAI(api_key=key, timeout=EMBEDDING_TIMEOUT_SECONDS, max_retries=EMBEDDING_MAX_RETRIES)
    return AsyncOpenAI(api_key=key, timeout=CHAT_TIMEOUT_SECONDS, max_retries=CHAT_MAX_RETRIES)
