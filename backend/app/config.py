"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./rental_desk.db"
    # Comma-separated list of browser origins allowed to call the API.
    cors_origins: str = "http://localhost:5173"
    # When true, requests may carry an X-Test-Clock header that replaces "now".
    allow_test_clock: bool = True
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def normalise_postgres_scheme(cls, value: str) -> str:
        # Render and Neon hand out postgres:// URLs; SQLAlchemy needs an explicit driver.
        if value.startswith("postgres://"):
            value = "postgresql://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
