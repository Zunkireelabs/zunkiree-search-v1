"""Test bootstrap — set the dummy env vars Pydantic Settings expects before
any `app.*` import resolves."""
import os

from cryptography.fernet import Fernet

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("PINECONE_API_KEY", "test")
os.environ.setdefault("PINECONE_HOST", "https://test.svc.pinecone.io")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("API_SECRET_KEY", "test")
# Generated per test session — never committed; never used in production.
os.environ.setdefault("BACKEND_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())


import pytest


@pytest.fixture(autouse=True)
def _isolate_clinic_session_state():
    """SBAL-Z14: clinic session state is module-level and keyed by session_id.
    Tests reuse ids like "s1"; the per-session flow-turn budget (F17) would
    otherwise accumulate across tests and trip a handoff in the sixth."""
    from app.services import clinic_tools

    clinic_tools._SESSION_STATE.clear()
    yield
    clinic_tools._SESSION_STATE.clear()
