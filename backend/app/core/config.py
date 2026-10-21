"""Application configuration loaded from environment variables / `.env`.

Every setting has a safe development default so the application can boot for a
smoke check, but security-sensitive values are validated in non-development
environments so a misconfigured deployment fails fast instead of running with
weak defaults.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ------------------------------------------------------
    app_name: str = "agentops"
    environment: Environment = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # --- Database ----------------------------------------------------------
    database_url: str = "postgresql+psycopg://agentops:agentops@127.0.0.1:5432/agentops"
    test_database_url: str | None = None
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_echo: bool = False

    # --- Security ----------------------------------------------------------
    session_secret: str = "development-insecure-secret-change-me"
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65_536
    argon2_parallelism: int = 4
    session_ttl_hours: int = 24
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Rate limiting -----------------------------------------------------
    rate_limit_enabled: bool = True
    auth_rate_limit_per_minute: int = 10

    # --- Model providers ----------------------------------------------------
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: int = 120
    default_model_provider_type: str = "ollama"
    default_model_name: str = "qwen2.5:7b-instruct"

    # --- Background jobs ----------------------------------------------------
    job_worker_enabled: bool = True
    job_worker_concurrency: int = 4
    job_lease_seconds: int = 120
    job_max_attempts: int = 5

    # --- Storage -----------------------------------------------------------
    storage_root: str = "./var/storage"
    storage_max_upload_mb: int = 25

    @field_validator("api_prefix")
    @classmethod
    def _normalize_prefix(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith("/"):
            value = f"/{value}"
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        """Allowed browser origins parsed from the comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production_like(self) -> bool:
        return self.environment in {"staging", "production"}

    @model_validator(mode="after")
    def _validate_security(self) -> Settings:
        if self.is_production_like:
            if len(self.session_secret) < 32 or self.session_secret.startswith("development-"):
                raise ValueError(
                    "SESSION_SECRET must be set to a strong (>=32 char) value outside development"
                )
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true outside development")
        return self

    @property
    def sync_database_url(self) -> str:
        """psycopg sync URL (used by tooling that cannot use the async driver)."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings", "Environment"]
