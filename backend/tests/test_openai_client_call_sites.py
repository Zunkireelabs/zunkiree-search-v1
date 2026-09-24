"""
P2 brief §7c B4 follow-up (2026-09-24), PR #88 review changes:

(a) ingestion.py's batch embeddings, profile_builder.py, and
    inbound_event_dispatcher.py move to the "background" profile
    (120s / 2 retries) so website ingest and profile builds don't start
    failing under the tight 15s/8s voice-budget bounds.
(b) max_retries=0 stays only on the voice-budget paths (clinic agent,
    default-RAG stream via llm.py); the async DM/hospitality agents get
    SDK-style retries (2) back via the "chat_retry" profile.

These assert each service actually wires up the intended profile, since
`test_openai_client.py` only covers the constructor itself.
"""
from app.services.openai_client import (
    BACKGROUND_MAX_RETRIES,
    BACKGROUND_TIMEOUT_SECONDS,
    CHAT_MAX_RETRIES,
    CHAT_RETRY_MAX_RETRIES,
    CHAT_TIMEOUT_SECONDS,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_TIMEOUT_SECONDS,
)


def test_clinic_agent_keeps_zero_retry_chat_profile():
    from app.services.clinic_agent import ClinicAgentService

    client = ClinicAgentService().client
    assert client.timeout == CHAT_TIMEOUT_SECONDS
    assert client.max_retries == CHAT_MAX_RETRIES == 0


def test_default_rag_llm_provider_keeps_zero_retry_chat_profile():
    # OpenAIProvider backs LLMService (the default-RAG stream's answer
    # call in api/query.py) — this is the voice-budget path, not the
    # provider passed by any agent.
    from app.services.llm import OpenAIProvider

    client = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini").client
    assert client.timeout == CHAT_TIMEOUT_SECONDS
    assert client.max_retries == CHAT_MAX_RETRIES == 0


def test_ecommerce_dm_agent_gets_retries_back():
    from app.services.agent import AgentService

    client = AgentService().client
    assert client.timeout == CHAT_TIMEOUT_SECONDS
    assert client.max_retries == CHAT_RETRY_MAX_RETRIES == 2


def test_hospitality_agent_gets_retries_back():
    from app.services.hospitality_agent import HospitalityAgentService

    client = HospitalityAgentService().client
    assert client.timeout == CHAT_TIMEOUT_SECONDS
    assert client.max_retries == CHAT_RETRY_MAX_RETRIES == 2


def test_profile_builder_uses_background_profile():
    from app.services.profile_builder import ProfileBuilderService

    client = ProfileBuilderService().client
    assert client.timeout == BACKGROUND_TIMEOUT_SECONDS == 120.0
    assert client.max_retries == BACKGROUND_MAX_RETRIES == 2


def test_hot_path_embedding_service_keeps_voice_budget_profile():
    from app.services.embeddings import get_embedding_service

    client = get_embedding_service().client
    assert client.timeout == EMBEDDING_TIMEOUT_SECONDS == 8.0
    assert client.max_retries == EMBEDDING_MAX_RETRIES == 1


def test_background_embedding_service_uses_background_profile():
    from app.services.embeddings import get_background_embedding_service

    client = get_background_embedding_service().client
    assert client.timeout == BACKGROUND_TIMEOUT_SECONDS == 120.0
    assert client.max_retries == BACKGROUND_MAX_RETRIES == 2


def test_hot_and_background_embedding_services_are_distinct_singletons():
    from app.services.embeddings import (
        get_background_embedding_service,
        get_embedding_service,
    )

    assert get_embedding_service() is get_embedding_service()
    assert get_background_embedding_service() is get_background_embedding_service()
    assert get_embedding_service() is not get_background_embedding_service()


def test_ingestion_service_uses_background_embedding_service():
    from app.services.embeddings import get_background_embedding_service
    from app.services.ingestion import IngestionService

    assert IngestionService().embedding_service is get_background_embedding_service()


def test_inbound_dispatcher_resolves_embeds_through_background_getter():
    import app.services.inbound_event_dispatcher as dispatcher
    from app.services.embeddings import get_background_embedding_service

    # The dispatcher's per-row embed call (handle_product_change) must
    # resolve through the background-profile getter, not the hot-path
    # get_embedding_service() the voice-budgeted RAG query path uses.
    assert dispatcher.get_background_embedding_service is get_background_embedding_service
    assert not hasattr(dispatcher, "get_embedding_service")
