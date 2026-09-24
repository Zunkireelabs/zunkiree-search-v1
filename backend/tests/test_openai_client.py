"""
P2 brief §7c B4 + follow-up (2026-09-24): every AsyncOpenAI( call site used
to build its client with no timeout/max_retries, leaving the SDK's ~600s
default in place. This asserts the shared constructor's four bounded
profiles: "embeddings" and "chat" (voice-budgeted), "chat_retry" (async
DM/hospitality agents, not voice-budgeted, SDK-style retries restored),
and "background" (ingestion/profile-builder/inbound-dispatcher bulk work).
"""
from app.services.openai_client import (
    BACKGROUND_MAX_RETRIES,
    BACKGROUND_TIMEOUT_SECONDS,
    CHAT_MAX_RETRIES,
    CHAT_RETRY_MAX_RETRIES,
    CHAT_TIMEOUT_SECONDS,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_TIMEOUT_SECONDS,
    get_openai_client,
)


def test_embeddings_profile_is_bounded():
    client = get_openai_client("embeddings")
    assert client.timeout == EMBEDDING_TIMEOUT_SECONDS == 8.0
    assert client.max_retries == EMBEDDING_MAX_RETRIES == 1


def test_chat_profile_is_bounded():
    client = get_openai_client("chat")
    assert client.timeout == CHAT_TIMEOUT_SECONDS == 15.0
    assert client.max_retries == CHAT_MAX_RETRIES == 0


def test_chat_retry_profile_keeps_timeout_but_restores_retries():
    # Same per-call bound as "chat" (still not voice-budgeted, so a call
    # can't run away), but SDK-style retries (2) restored since the async
    # DM/hospitality agents aren't racing a hard turn deadline.
    chat_retry_client = get_openai_client("chat_retry")
    chat_client = get_openai_client("chat")
    assert chat_retry_client.timeout == chat_client.timeout == CHAT_TIMEOUT_SECONDS
    assert chat_retry_client.max_retries == CHAT_RETRY_MAX_RETRIES == 2
    assert chat_retry_client.max_retries != chat_client.max_retries


def test_background_profile_is_generous():
    client = get_openai_client("background")
    assert client.timeout == BACKGROUND_TIMEOUT_SECONDS == 120.0
    assert client.max_retries == BACKGROUND_MAX_RETRIES == 2


def test_default_kind_is_chat():
    default_client = get_openai_client()
    chat_client = get_openai_client("chat")
    assert default_client.timeout == chat_client.timeout
    assert default_client.max_retries == chat_client.max_retries


def test_no_profile_uses_sdk_unbounded_timeout():
    # openai's SDK default is a ~600s timeout — regression guard against a
    # future edit accidentally reverting any profile to an unbounded client.
    for kind in ("embeddings", "chat", "chat_retry", "background"):
        client = get_openai_client(kind)
        assert client.timeout < 600.0


def test_voice_budget_profiles_keep_zero_or_one_retry():
    # "embeddings" and "chat" back the voice-budgeted paths (clinic agent,
    # default-RAG stream) — a retry there risks blowing the turn's hard
    # deadline, so these must stay well under the SDK's default of 2.
    for kind in ("embeddings", "chat"):
        client = get_openai_client(kind)
        assert client.max_retries < 2


def test_unknown_kind_falls_back_to_chat_profile():
    client = get_openai_client("not-a-real-profile")
    chat_client = get_openai_client("chat")
    assert client.timeout == chat_client.timeout
    assert client.max_retries == chat_client.max_retries


def test_api_key_override_is_used():
    client = get_openai_client("chat", api_key="tenant-specific-key")
    assert client.api_key == "tenant-specific-key"
