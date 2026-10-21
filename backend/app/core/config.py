"""Application configuration loaded from environment variables / `.env`.

Every setting has a safe development default so the application can boot for a
smoke check, but security-sensitive values are validated in non-development
environments so a misconfigured deployment fails fast instead of running with
weak defaults.

Identity is owned by **Supabase Auth** in every deployed environment. The
``local`` auth mode exists only so the product can be developed and tested
without a hosted project; it issues its own HS256 tokens and refuses to start
outside development/test (see ``_validate_auth``).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
AuthMode = Literal["local", "supabase"]

LOCAL_AUTH_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test"})


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
    # Supabase Postgres through the transaction pooler in deployed
    # environments. The development default points at the project-local
    # cluster created by `scripts/dev_db.ps1` (port 55432).
    database_url: str = "postgresql+psycopg://agentops@127.0.0.1:55432/agentops"
    test_database_url: str | None = "postgresql+psycopg://agentops@127.0.0.1:55432/agentops_test"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_echo: bool = False
    db_statement_timeout_ms: int = 15_000
    db_idle_tx_timeout_ms: int = 30_000

    # --- Identity ----------------------------------------------------------
    auth_mode: AuthMode = "local"

    # Supabase (required when auth_mode = "supabase")
    supabase_url: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: str | None = None
    supabase_jwks_url: str | None = None
    supabase_jwks_cache_seconds: int = 600

    # Local development issuer (never used when auth_mode = "supabase")
    # Deliberately weak, development-only default. `_validate_auth` refuses to
    # start outside development/test with the local issuer enabled, and the
    # value is overridden from the environment in every real deployment.
    local_jwt_secret: str = "development-insecure-jwt-secret-change-me"  # noqa: S105
    local_jwt_issuer: str = "agentops-local"
    local_jwt_ttl_minutes: int = 480

    # --- Passwords (development-only credentials) --------------------------
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65_536
    argon2_parallelism: int = 4

    # --- HTTP ---------------------------------------------------------------
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

    @field_validator("supabase_url", "supabase_jwks_url", "supabase_jwt_issuer")
    @classmethod
    def _strip_optional_url(cls, value: str | None) -> str | None:
        return value.strip().rstrip("/") if value and value.strip() else None

    @property
    def cors_origin_list(self) -> list[str]:
        """Allowed browser origins parsed from the comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production_like(self) -> bool:
        return self.environment in {"staging", "production"}

    @property
    def jwks_url(self) -> str | None:
        """Supabase JWKS endpoint (explicit setting wins over the derived URL)."""
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"
        return None

    @property
    def jwt_issuer(self) -> str | None:
        """Expected ``iss`` claim for Supabase access tokens."""
        if self.supabase_jwt_issuer:
            return self.supabase_jwt_issuer
        if self.supabase_url:
            return f"{self.supabase_url}/auth/v1"
        return None

    @model_validator(mode="after")
    def _validate_auth(self) -> Settings:
        if self.auth_mode == "supabase":
            if not self.supabase_url:
                raise ValueError("SUPABASE_URL is required when AUTH_MODE=supabase")
            if not self.jwks_url:
                raise ValueError("SUPABASE_JWKS_URL or SUPABASE_URL must be configured")
            if not self.jwt_issuer:
                raise ValueError("SUPABASE_JWT_ISSUER or SUPABASE_URL must be configured")
        else:
            # The local issuer is a development convenience, never a deployment
            # posture: it must not be able to mint production identities.
            if self.environment not in LOCAL_AUTH_ENVIRONMENTS:
                raise ValueError(
                    "AUTH_MODE=local is only allowed in development or test. "
                    "Configure Supabase Auth (AUTH_MODE=supabase) for this environment."
                )
            if self.is_production_like:  # pragma: no cover - covered by the check above
                raise ValueError("AUTH_MODE=local is not permitted in production-like environments")
            if len(self.local_jwt_secret) < 32:
                raise ValueError("LOCAL_JWT_SECRET must be at least 32 characters long")
        return self

    @property
    def sync_database_url(self) -> str:
        """psycopg sync URL (used by tooling that cannot use the async driver)."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")

    @property
    def local_auth_enabled(self) -> bool:
        return self.auth_mode == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()


settings = get_settings()

__all__ = [
    "LOCAL_AUTH_ENVIRONMENTS",
    "AuthMode",
    "Environment",
    "Settings",
    "get_settings",
    "settings",
]
