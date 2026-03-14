from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database — accepts both postgresql:// and postgresql+asyncpg:// formats
    DATABASE_URL: str

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # JWT
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    SESSION_INACTIVITY_HOURS: int = 8

    # Bootstrap (remove from .env after first admin registers)
    INITIAL_ADMIN_TOKEN: str | None = None

    # Application
    APP_URL: str
    APP_VERSION: str = "1.0.0"

    # GitHub Bridge
    GITHUB_TOKEN_ENCRYPTION_KEY: str

    # Admin
    ADMIN_TOKEN: str | None = None

    # Ingestion Pipeline — Epic 3
    GCS_BUCKET_NAME: str = "marketing-ingestion"
    WORKER_CONCURRENCY: int = 5

    # Agentic Chat / RAG — Epic 4
    VOYAGE_API_KEY: str | None = None
    KB_SIMILARITY_THRESHOLD: float = 0.3
    KB_RETRIEVAL_TOP_K: int = 6
    CHAT_MODEL: str = "claude-opus-4-6"
    CHAT_MAX_TOKENS: int = 1024
    KB_INDEX_CONCURRENCY: int = 2

    # Content Sync — Epic 6
    SYNC_INTERVAL_HOURS: int = 24
    GITHUB_MERGE_METHOD: str = "merge"

    # SMTP
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str


settings = Settings()


def get_settings() -> Settings:
    """Return the module-level Settings singleton.

    Provided as a callable for dependency injection and for utilities that
    need to avoid a module-level import of ``settings`` directly.
    """
    return settings
