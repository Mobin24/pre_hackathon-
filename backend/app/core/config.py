"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized settings sourced from backend/.env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    app_env: str = Field(default="development", alias="APP_ENV")
    app_port: int = Field(default=8000, alias="APP_PORT")

    # AI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    # Cheap text-only model for cheap structured extraction.
    openai_text_model: str = Field(default="gpt-4o-mini", alias="OPENAI_TEXT_MODEL")
    # Moderate vision-capable model for image analysis.
    openai_vision_model: str = Field(default="gpt-4o-mini", alias="OPENAI_VISION_MODEL")
    # Cheapest model for rolling up many reports into a situation summary.
    openai_summary_model: str = Field(default="gpt-4o-mini", alias="OPENAI_SUMMARY_MODEL")
    # Soft timeout for any single AI call (seconds).
    openai_timeout_seconds: float = Field(default=20.0, alias="OPENAI_TIMEOUT_SECONDS")
    # Auto-recovery threshold in seconds for stuck `pending_ai` docs.
    ai_recovery_threshold_seconds: int = Field(default=60, alias="AI_RECOVERY_THRESHOLD_SECONDS")
    # How often the background task generates a fresh global sitrep.
    # Set to 0 to disable (admin still has POST /api/sitrep/generate).
    # Default: 3600 seconds = 1 hour. Overridable via SITREP_TICK_SECONDS env.
    sitrep_tick_seconds: float = Field(default=3600.0, alias="SITREP_TICK_SECONDS")

    # MongoDB
    mongodb_uri: str = Field(default="", alias="MONGODB_URI")
    mongodb_db_name: str = Field(default="drrcs_dev", alias="MONGODB_DB_NAME")

    # CORS
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    # JWT / Auth
    jwt_secret: str = Field(default="change-me-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    token_expiry_minutes: int = Field(default=60 * 24, alias="TOKEN_EXPIRY_MINUTES")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
