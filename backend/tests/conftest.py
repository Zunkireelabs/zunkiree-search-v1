"""Test bootstrap — set the dummy env vars Pydantic Settings expects before
any `app.*` import resolves."""
import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("PINECONE_API_KEY", "test")
os.environ.setdefault("PINECONE_HOST", "https://test.svc.pinecone.io")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("API_SECRET_KEY", "test")
