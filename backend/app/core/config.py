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
    embedding_model: str = ""
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
