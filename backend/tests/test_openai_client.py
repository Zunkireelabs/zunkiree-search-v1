"""
P2 brief §7c B4: every AsyncOpenAI( call site used to build its client with
no timeout/max_retries, leaving the SDK's ~600s default in place. This
asserts the shared constructor's two bounded profiles.
"""
from app.services.openai_client import (
    CHAT_MAX_RETRIES,
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


def test_default_kind_is_chat():
    default_client = get_openai_client()
    chat_client = get_openai_client("chat")
    assert default_client.timeout == chat_client.timeout
    assert default_client.max_retries == chat_client.max_retries


def test_neither_profile_uses_sdk_defaults():
    # openai's SDK default is a 600s timeout / 2 retries — regression guard
    # against a future edit accidentally reverting to unbounded clients.
    for kind in ("embeddings", "chat"):
        client = get_openai_client(kind)
        assert client.timeout < 600.0
        assert client.max_retries < 2


def test_api_key_override_is_used():
    client = get_openai_client("chat", api_key="tenant-specific-key")
    assert client.api_key == "tenant-specific-key"
