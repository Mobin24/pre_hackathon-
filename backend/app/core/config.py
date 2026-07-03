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
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

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
