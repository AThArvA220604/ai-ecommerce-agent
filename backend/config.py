"""
Centralized configuration loaded from environment variables.
Validated at startup — fail fast on bad config instead of dying mid-request.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    db_path: str = Field(default="ecommerce.db", description="SQLite path for local dev")

    # AI engine
    use_llm: bool = Field(default=False, description="If true, route classification through OpenAI")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="Model name for classification")
    openai_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    openai_max_retries: int = Field(default=2, ge=0, le=5)

    # Circuit breaker — trip after N consecutive failures, cool down for M seconds
    llm_failure_threshold: int = Field(default=3, ge=1)
    llm_cooldown_seconds: int = Field(default=60, ge=5)

    # Server
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    @property
    def ai_engine_active(self) -> bool:
        """True only when LLM mode is requested AND a key is present."""
        return self.use_llm and bool(self.openai_api_key)

    @property
    def engine_mode(self) -> str:
        """Human-readable label for the /health endpoint."""
        if not self.use_llm:
            return "rules"
        if not self.openai_api_key:
            return "rules (LLM requested but no API key)"
        return "llm"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton — read from env once per process."""
    return Settings()
