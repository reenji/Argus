"""Environment-backed configuration for the hosted API."""

from __future__ import annotations

from dataclasses import dataclass, field
import os


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        value.strip().rstrip("/")
        for value in os.environ.get(name, default).split(",")
        if value.strip()
    )


@dataclass(frozen=True)
class Settings:
    environment: str = os.environ.get("ARGUS_ENV", "development").lower()
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "sqlite:///./tmp/argus_web.db",
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.environ.get("JWT_SECRET", "local-development-only-change-me")
    encryption_key: str = os.environ.get("ARGUS_ENCRYPTION_KEY", "")
    access_token_minutes: int = int(os.environ.get("ACCESS_TOKEN_MINUTES", "1440"))
    data_retention_days: int = int(os.environ.get("ARGUS_DATA_RETENTION_DAYS", "90"))
    cors_origins: tuple[str, ...] = _csv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    chat_model: str = os.environ.get("ARGUS_CHAT_MODEL", "gemini-2.5-flash")
    # Where the real client address comes from behind a proxy. X-Forwarded-For
    # is client-controlled except for the hops the platform proxies append.
    client_ip_header: str = os.environ.get("CLIENT_IP_HEADER", "").strip()
    trusted_proxy_hops: int = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))
    chat_timeout_seconds: float = float(os.environ.get("ARGUS_CHAT_TIMEOUT_SECONDS", "60"))
    auto_create_tables: bool = os.environ.get("AUTO_CREATE_TABLES", "1").lower() in {
        "1", "true", "yes", "on",
    }
    # Without Redis each process keeps its own counters, which multiplies
    # every limit by the number of workers, so production refuses to start.
    redis_required: bool = field(default_factory=lambda: os.environ.get(
        "REDIS_REQUIRED",
        "1" if os.environ.get("ARGUS_ENV", "development").lower() == "production" else "0",
    ).lower() in {"1", "true", "yes", "on"})

    def validate_production(self) -> None:
        if self.data_retention_days < 1:
            raise RuntimeError("ARGUS_DATA_RETENTION_DAYS must be at least 1")
        if self.chat_timeout_seconds <= 0:
            raise RuntimeError("ARGUS_CHAT_TIMEOUT_SECONDS must be positive")
        if self.environment != "production":
            return
        if self.jwt_secret == "local-development-only-change-me":
            raise RuntimeError("JWT_SECRET must be configured in production")
        if not self.encryption_key:
            raise RuntimeError("ARGUS_ENCRYPTION_KEY must be configured in production")
        if not self.database_url.startswith(("postgresql://", "postgres://", "postgresql+")):
            raise RuntimeError("Production DATABASE_URL must point to Postgres")


settings = Settings()
