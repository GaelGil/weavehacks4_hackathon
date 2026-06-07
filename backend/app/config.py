"""Central configuration, loaded from environment / .env."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"  # reasoning/judgment (advisor, researcher)
    openai_vision_model: str = (
        "gpt-4o-mini"  # cheap screen scraping (collector, redactor)
    )
    openai_embed_model: str = "text-embedding-3-small"

    # Weave
    wandb_api_key: str = ""
    weave_project: str = "scamguard"
    weave_disabled: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379"
    API_V1_STR: str = "/api/v1"
    # Server
    scan_interval_seconds: int = 30
    allowed_origins: str = "http://localhost:5173,http://localhost:4000"
    WANDB_WEAVE_PROJECT: str | None = None
    WANDB_API_KEY: str | None = None

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def model_post_init(self, __context) -> None:
        # The OpenAI Agents SDK / OpenAI client read os.environ directly, not this
        # Settings object. Mirror the loaded keys into the process environment so
        # they pick them up. (Only set if non-empty; never clobber a real env var.)
        if self.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.wandb_api_key and not os.environ.get("WANDB_API_KEY"):
            os.environ["WANDB_API_KEY"] = self.wandb_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
