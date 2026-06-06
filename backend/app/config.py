"""Central configuration, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embed_model: str = "text-embedding-3-small"

    # Weave
    wandb_api_key: str = ""
    weave_project: str = "scamguard"
    weave_disabled: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Server
    scan_interval_seconds: int = 30
    allowed_origins: str = "http://localhost:5173,http://localhost:4000"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
