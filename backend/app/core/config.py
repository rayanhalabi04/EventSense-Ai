from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/eventsense_ai"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "eventsense_ai"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str = "redis://localhost:6379/0"
    memory_enabled: bool = False
    short_term_memory_ttl_seconds: int = 604800
    short_term_memory_max_messages: int = 10
    jwt_secret_key: str = "change-me-in-local-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    llm_enabled: bool = False
    llm_provider: str = "gemini"
    llm_timeout_seconds: float = 10.0
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # --- RAG embeddings ---------------------------------------------------
    # Which embedding backend powers tenant-scoped RAG retrieval.
    #   "fallback" (default) -> deterministic, NON-SEMANTIC keyword/hash vectors
    #   "gemini" / "openai"  -> real semantic embeddings (needs an API key)
    embedding_provider: str = "fallback"
    # Model id for the selected semantic provider. Empty -> provider default
    # (gemini: text-embedding-004, openai: text-embedding-3-small).
    embedding_model: str = ""
    # Vector dimension stored in pgvector. Must match the embedding model.
    # 768 is the native size of Gemini text-embedding-004; OpenAI v3 models
    # are asked to emit this size via their `dimensions` parameter.
    embedding_dim: int = 768
    # Optional dedicated key for the embedding provider. When empty the
    # provider reuses the matching LLM key (gemini_api_key / openai_api_key).
    embedding_api_key: str = ""
    # When true, an unconfigured/unavailable semantic provider safely degrades
    # to the deterministic fallback instead of failing. When false, startup
    # fails fast if the configured semantic provider has no key.
    embedding_fallback_enabled: bool = True
    # Embedding provider request timeout (seconds).
    embedding_timeout_seconds: float = 15.0
    # Minimum cosine similarity for a retrieved chunk to count as relevant when
    # SEMANTIC embeddings are active. Real embedding models have a high baseline
    # similarity: with gemini-embedding-001 truncated to 768 dims, out-of-domain
    # queries still score ~0.43-0.51 against tenant docs, while genuine in-domain
    # questions score ~0.67-0.73. 0.6 sits in that gap so unsupported questions
    # refuse cleanly while supported ones still match. Tune per embedding model.
    rag_semantic_min_score: float = 0.6
    intent_classifier_artifact_path: str = (
        "app/ml/intent_classifier/artifacts/eventsense_tfidf_logreg_baseline.joblib"
    )
    intent_classifier_model_version: str = "tfidf-logreg-baseline"
    # Comma-separated list of origins allowed to call the API from a browser
    # (the EventSense AI frontend dev/preview servers by default).
    cors_allow_origins: str = "http://localhost:5173,http://localhost:4173"

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
