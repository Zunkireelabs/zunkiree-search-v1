from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache


class Settings(BaseSettings):
    # Environment
    environment: str = "production"  # development, staging, production

    # OpenAI
    openai_api_key: str

    # Pinecone
    pinecone_api_key: str
    pinecone_host: str
    pinecone_index_name: str = "zunkiree-search"

    # Database
    database_url: str

    @model_validator(mode="after")
    def fix_database_url(self):
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self

    # App
    api_secret_key: str = "change-this-in-production"
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # Query settings
    max_query_length: int = 500
    top_k_chunks: int = 5
    confidence_threshold: float = 0.25

    # LLM Configuration
    llm_provider: str = "openai"  # Future: anthropic, azure, etc.
    llm_model: str = "gpt-4o-mini"  # Default: cheap, fast model
    llm_model_premium: str = "gpt-4o"  # Premium: for complex/enterprise queries
    llm_temperature: float = 0.3
    llm_max_tokens: int = 500

    # SMTP / Email verification
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # eSewa
    esewa_merchant_code: str = ""
    esewa_secret_key: str = ""
    esewa_sandbox: bool = True

    # Khalti
    khalti_secret_key: str = ""
    khalti_sandbox: bool = True

    # Embeddings
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072

    # Agenticom Sync (legacy global secret; per-tenant credentials in tenant_backend_credentials)
    agenticom_api_url: str = ""  # e.g., https://api-agenticom.zunkireelabs.com
    agenticom_sync_secret: str = ""  # Shared secret for X-Sync-Secret header (legacy fallback only)

    # Per-tenant backend credentials encryption (Z2)
    backend_credentials_encryption_key: str = ""  # Fernet key, required before any per-tenant credential row is created

    # Z6 — per-tenant admin API for Stella callers
    master_admin_key: str = ""  # Required for tenant create/delete; empty → master endpoints hard-fail 401 master_admin_key_not_configured
    widget_script_base_url: str = ""  # Vercel CDN base for the embed bundle, e.g. https://zunkiree-search-v1.vercel.app

    # Meta Messaging / Chatbot
    meta_app_secret: str = ""
    meta_verify_token: str = ""
    chatbot_encryption_key: str = ""  # Fernet key for encrypting page_access_tokens
    chatbot_max_history: int = 10
    chatbot_conversation_ttl_days: int = 7

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
