from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MOCK_", extra="ignore")

    port: int = 8000
    log_level: str = "INFO"

    product_count: int = 200
    seed: int = 42
    mutation_interval: float = 0.0
    cdms_webhook_url: str = "http://localhost:8001/api/v1/webhooks/inventory"
    fault_timeout_seconds: float = 30.0
    webhook_timeout_seconds: float = 10.0

    warehouse_codes: list[str] = ["KQ7", "KV3"]
    condition_codes: list[str] = ["NEW", "DAMAGED"]
    unit_codes: list[str] = ["CAI", "BOX"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
