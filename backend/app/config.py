from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str

    # Pinecone
    pinecone_api_key: str
    pinecone_host: str
    pinecone_index_name: str = "zunkiree-search"

    # Database
    database_url: str

    # App
    api_secret_key: str = "change-this-in-production"
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # Query settings
    max_query_length: int = 500
    top_k_chunks: int = 5

    # LLM Configuration
    llm_provider: str = "openai"  # Future: anthropic, azure, etc.
    llm_model: str = "gpt-4o-mini"  # Default: cheap, fast model
    llm_model_premium: str = "gpt-4o"  # Premium: for complex/enterprise queries
    llm_temperature: float = 0.3
    llm_max_tokens: int = 500

    # Embeddings
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
