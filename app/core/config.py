"""Typed, environment-driven application configuration."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "staging", "prod", "test"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

ASYNC_POSTGRES_SCHEME = "postgresql+asyncpg://"


class Settings(BaseSettings):
    """Application settings loaded from environment variables (and `.env` in development).

    Field names map to upper-case env vars, e.g. ``app_env`` -> ``APP_ENV``.
    Secrets have no defaults and are held as ``SecretStr`` so they never appear in
    reprs or logs. ``hide_input_in_errors`` stops validation errors echoing raw values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Application
    app_name: str = "cloud-native-fastapi-platform"
    app_version: str = "0.1.0"
    app_env: Environment = "dev"
    log_level: LogLevel = "INFO"
    aws_region: str = "eu-west-2"

    # Database (DATABASE_URL is a secret: it embeds credentials)
    database_url: SecretStr | None = None
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1, description="Seconds to wait for a connection")
    db_pool_recycle: int = Field(default=1800, ge=-1, description="Seconds; -1 disables recycling")
    db_echo: bool = False

    # Authentication (OIDC/OAuth2/JWT). All three must be set together; unset means
    # auth is disabled (only sensible in dev, for working on unauthenticated concerns).
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])

    # Messaging (SQS). Unlike DATABASE_URL/OIDC, optional in every environment: if unset,
    # domain events fall back to LoggingEventPublisher rather than the app failing to start
    # (see app/main.py) - so the service is deployable before queue infrastructure exists.
    sqs_queue_url: str | None = None
    # EventBridge: event *routing* for other consumers/integrations, distinct from SQS's
    # role as the worker's durable work queue (ADR-004). Also optional everywhere; an app
    # with neither configured still runs, falling back to LoggingEventPublisher.
    eventbridge_bus_name: str | None = None

    @field_validator("database_url")
    @classmethod
    def _validate_database_scheme(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith(ASYNC_POSTGRES_SCHEME):
            raise ValueError(f"DATABASE_URL must use the {ASYNC_POSTGRES_SCHEME} scheme")
        return value

    @model_validator(mode="after")
    def _require_database_outside_dev(self) -> Self:
        if self.app_env in {"staging", "prod"} and self.database_url is None:
            raise ValueError("DATABASE_URL is required in staging and prod")
        return self

    @model_validator(mode="after")
    def _require_oidc_settings_together(self) -> Self:
        oidc_fields = (self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)
        if any(oidc_fields) and not all(oidc_fields):
            raise ValueError("OIDC_ISSUER, OIDC_AUDIENCE and OIDC_JWKS_URL must be set together")
        return self

    @model_validator(mode="after")
    def _require_oidc_outside_dev(self) -> Self:
        if self.app_env in {"staging", "prod"} and self.oidc_issuer is None:
            raise ValueError("OIDC settings are required in staging and prod")
        return self

    @property
    def auth_enabled(self) -> bool:
        return self.oidc_issuer is not None

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are exposed in non-production environments only."""
        return self.app_env != "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
