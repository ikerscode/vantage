from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres
    database_url: str = "postgresql+psycopg://vantage:changeme-dev@localhost:5432/vantage"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # MinIO / S3
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "vantage-minio"
    s3_secret_access_key: str = "changeme-dev"
    s3_region: str = "us-east-1"
    s3_bucket_analysis: str = "vantage-analysis"
    s3_use_ssl: bool = False

    # STAC / imagery source
    imagery_source: str = "earth_search"  # "earth_search" | "pgstac" (TODO(v2), not implemented)
    stac_api_url: str = "https://earth-search.aws.element84.com/v1"
    stac_default_collection: str = "sentinel-2-l2a"

    # Auth (dev JWT stub — NOT a real IdP; see app.core.security)
    jwt_secret: str = "change-me-dev-secret"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "vantage-dev"
    jwt_audience: str = "vantage-api"
    jwt_expire_minutes: int = 60
    # The single dev user issued by /api/auth/dev-token. Env-driven (not a
    # code literal) so a deployment can at least identify who "dev-analyst"
    # is instead of every environment sharing the exact same identity.
    dev_user_sub: str = "dev-analyst"
    dev_user_name: str = "Dev Analyst"
    dev_user_roles: Annotated[list[str], NoDecode] = ["analyst"]

    # Tiler
    tiler_base_url: str = "http://localhost:8001"
    tiler_public_base_url: str = "http://localhost:8001"

    # Inference (placeholder detection)
    inference_base_url: str = "http://localhost:8002"

    # Change detection / monitoring
    change_detection_default_threshold: float = 0.2
    monitor_sweep_interval_seconds: int = 300

    # CORS. NoDecode: pydantic-settings otherwise JSON-decodes list-typed env
    # vars, but .env files write this as a plain comma-separated string.
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("cors_allowed_origins", "dev_user_roles", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        # pydantic-settings JSON-decodes list-typed env vars by default; accept
        # a plain comma-separated string too since that's what .env files use.
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
