from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CDMS_",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://cdms:cdms@localhost:5432/cdms"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: float = 10.0
    db_statement_timeout_ms: int = 15_000
    db_connect_retries: int = 30
    db_connect_retry_delay: float = 1.0

    inventory_base_url: str = "http://localhost:8000"
    inventory_timeout_seconds: float = 5.0
    inventory_retries: int = 2
    inventory_retry_backoff: float = 0.25

    poll_enabled: bool = False
    poll_interval_seconds: int = 60
    poll_page_size: int = 100
    poll_max_pages: int = 200
    poll_startup_delay_seconds: float = 3.0

    webhook_shared_secret: str | None = None

    ignored_fields: dict[str, list[str]] = Field(default_factory=dict)

    auto_create_schema: bool = False
    log_level: str = "INFO"

    def ignored_for(self, entity_type: str) -> frozenset[str]:
        return frozenset(self.ignored_fields.get(entity_type, ()))


@lru_cache
def get_settings() -> Settings:
    return Settings()
