"""
Typed application configuration via pydantic-settings.

Why pydantic-settings instead of reading os.environ everywhere: one typed,
validated source of truth for config, with defaults and clear failure when a
required value is malformed. This is the same `BaseSettings` pattern the
interview Q&A calls out (Q25).
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Django ---
    django_secret_key: str = Field(default="dev-insecure-change-me", alias="DJANGO_SECRET_KEY")
    django_debug: bool = Field(default=False, alias="DJANGO_DEBUG")
    django_allowed_hosts: str = Field(default="localhost,127.0.0.1", alias="DJANGO_ALLOWED_HOSTS")

    # --- MongoDB ---
    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    mongo_db: str = Field(default="flydesk", alias="MONGO_DB")

    # --- Redis (offer cache, idempotency reservation) ---
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    offer_cache_ttl: int = Field(default=60, alias="OFFER_CACHE_TTL")  # seconds

    # --- Kafka (event streaming: outbox relay + consumers) ---
    kafka_bootstrap_servers: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")

    # --- Observability ---
    environment: str = Field(default="development", alias="FLYDESK_ENV")
    log_json: bool = Field(default=False, alias="LOG_JSON")  # JSON logs in prod
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")  # empty -> Sentry off

    # --- Duffel ---
    duffel_api_token: str = Field(default="", alias="DUFFEL_API_TOKEN")
    duffel_api_url: str = Field(default="https://api.duffel.com", alias="DUFFEL_API_URL")
    duffel_api_version: str = Field(default="v2", alias="DUFFEL_API_VERSION")

    # --- Provider selection (duffel | amadeus) ---
    provider: str = Field(default="duffel", alias="FLYDESK_PROVIDER")

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.django_allowed_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so we build/validate Settings exactly once per process."""
    return Settings()
