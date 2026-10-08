"""Test bootstrap — set the dummy env vars Pydantic Settings expects before
any `app.*` import resolves."""
import os

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("PINECONE_API_KEY", "test")
os.environ.setdefault("PINECONE_HOST", "https://test.svc.pinecone.io")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("API_SECRET_KEY", "test")
# Generated per test session — never committed; never used in production.
os.environ.setdefault("BACKEND_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())


# Education taps are validated against the block they claim to come from (education_actions.py). These older agent
# tests drive the agent with hand-made taps whose block ids were never shown, so they run with validation off.
# New tests turn it on explicitly (see tests/test_education_actions.py).
_LEGACY_UNVALIDATED_TAP_MODULES = {"test_education_agent.py", "test_education_followup.py"}

# Compositions show a result card with its companions (profile summary, next-step buttons). These older tests assert a
# turn shows exactly one block ("[card] = blocks_of(...)"), so they run with compositions off. New tests cover the
# composed turns explicitly (see tests/test_education_compositions.py).
_LEGACY_SINGLE_BLOCK_MODULES = {"test_education_agent.py", "test_education_followup.py"}


@pytest.fixture(autouse=True)
def _legacy_agent_tests_skip_tap_validation(request, monkeypatch):
    if request.node.fspath.basename in _LEGACY_UNVALIDATED_TAP_MODULES:
        from app.services import education_agent
        monkeypatch.setattr(education_agent.settings, "education_validate_block_actions", False)


@pytest.fixture(autouse=True)
def _legacy_agent_tests_show_single_blocks(request, monkeypatch):
    if request.node.fspath.basename in _LEGACY_SINGLE_BLOCK_MODULES:
        from app.services import education_agent
        monkeypatch.setattr(education_agent.settings, "education_compositions", False)

# Card lead-ins are written by code (education_leadins.py), so a card turn makes no LLM call. These tests script the LLM's
# lead-in and inspect its call, so they run with templated lead-ins off. New tests cover the templated turns explicitly
# (see tests/test_education_leadins.py).
_LEGACY_LLM_LEADIN_MODULES = {"test_education_agent.py", "test_education_followup.py", "test_education_compositions.py"}


@pytest.fixture(autouse=True)
def _legacy_agent_tests_use_llm_leadins(request, monkeypatch):
    if request.node.fspath.basename in _LEGACY_LLM_LEADIN_MODULES:
        from app.services import education_agent
        monkeypatch.setattr(education_agent.settings, "education_template_leadins", False)

