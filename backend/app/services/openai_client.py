"""
Single constructor for every AsyncOpenAI client in the app.

Every call site used to build `AsyncOpenAI(api_key=...)` with no `timeout`
or `max_retries`, which leaves the SDK defaults in place: ~600s timeout,
2 retries. A stalled OpenAI call under those defaults can hang a request
for up to ~10 minutes with no error surfaced to the client — and, on the
default-RAG path, pins a DB pooler connection idle-in-transaction for the
same span (see P2 brief §7c B4; reproduced on stage 2026-09-24).

Four bounded profiles. The first two exist so a voice turn fails cleanly
inside Orca's 25s run timeout instead of hanging past it; the other two
cover paths that are not voice-budgeted and were getting starved by the
same 15s/0-retry "chat" bound applied to everything (P2 brief §7c B4
follow-up, 2026-09-24):

- "embeddings": text-embedding-3-large calls in the hot RAG retrieval
  path. 8s timeout, 1 retry (~16s worst case for the single call). This
  is normally the very first external call in a turn, so 16s still
  leaves headroom under the 25s budget.
- "chat": voice-budget chat/completions calls only — the clinic agent
  tool-loop (`clinic_agent.py`) and the default-RAG stream's answer call
  (`llm.py`, `api/query.py`'s `/query/stream`). 15s timeout, 0 retries,
  so no single call can ever exceed ~15s. Multi-tool agent turns chain
  several of these calls; capping each one individually (rather than
  doubling any of them via a retry) keeps the turn's own iteration/
  turn-level timeout the thing that bounds total turn duration, not a
  single retried call.
- "chat_retry": chat/completions calls for the async DM/hospitality
  agents (`agent.py` — serves kasa-clothing's prod Instagram —, and
  `hospitality_agent.py`). These aren't voice-budgeted, so a retry no
  longer risks blowing a hard turn deadline; giving them SDK-style
  retries back (2, the SDK default) trades a bit of worst-case latency
  for not failing an IG DM turn on a single transient OpenAI hiccup.
  Same 15s per-call timeout as "chat".
- "background": everything that runs off a synchronous request/response
  turn — ingestion's batch embeddings (`ingestion.py`), the business
  profile builder (`profile_builder.py`; its extraction call uses
  `max_tokens=2000`, which won't reliably fit inside the 15s "chat"
  bound), and the inbound webhook dispatcher (`inbound_event_dispatcher.py`).
  120s timeout, 2 retries — generous, because a website ingest or a
  profile build failing outright is worse than it taking longer.

All profiles fail with `openai.APITimeoutError` (a subclass of
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
CHAT_RETRY_MAX_RETRIES = 2
BACKGROUND_TIMEOUT_SECONDS = 120.0
BACKGROUND_MAX_RETRIES = 2

_PROFILES = {
    "embeddings": (EMBEDDING_TIMEOUT_SECONDS, EMBEDDING_MAX_RETRIES),
    "chat": (CHAT_TIMEOUT_SECONDS, CHAT_MAX_RETRIES),
    "chat_retry": (CHAT_TIMEOUT_SECONDS, CHAT_RETRY_MAX_RETRIES),
    "background": (BACKGROUND_TIMEOUT_SECONDS, BACKGROUND_MAX_RETRIES),
}


def get_openai_client(kind: str = "chat", api_key: str | None = None) -> AsyncOpenAI:
    """Build a bounded AsyncOpenAI client.

    Args:
        kind: "embeddings", "chat" (default), "chat_retry", or "background".
            Picks the timeout/retry profile.
        api_key: Overrides `settings.openai_api_key` (e.g. a per-tenant key).
    """
    if kind not in _PROFILES:
        raise ValueError(
            f"get_openai_client: unknown profile kind={kind!r}, expected one of {sorted(_PROFILES)}"
        )
    settings = get_settings()
    key = api_key or settings.openai_api_key
    timeout, max_retries = _PROFILES[kind]
    return AsyncOpenAI(api_key=key, timeout=timeout, max_retries=max_retries)
