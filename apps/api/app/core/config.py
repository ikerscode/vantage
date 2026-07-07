from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# SEC-04: secrets that must never survive into a production boot. Matches
# every literal in infra/.env.example / infra/db-init/01-roles.sql.template —
# if either of those files' placeholder text changes, update this list too.
_KNOWN_DEFAULT_SECRETS = {
    "changeme-dev",
    "changeme-app-dev",
    "changeme-migrate-dev",
    "change-me-dev-secret",
    "change-me-dev-tiler-token",
    "change-me-dev-inference-token",
}
_MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SEC-04/SEC-02: gates every fail-closed check below. "development" is
    # the default so `docker-compose.yml`'s known dev-convenience secrets
    # keep working for local dev without a boot-time refusal; the packaged
    # app's docker-compose.prod.yml sets this to "production" explicitly.
    vantage_env: Literal["development", "production"] = "development"

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
    # "earth_search" | "static_catalog" (bundled demo scenes, BRIEF v1.3 §6)
    # | "pgstac" (TODO(v2), not implemented)
    imagery_source: str = "earth_search"
    stac_api_url: str = "https://earth-search.aws.element84.com/v1"
    stac_default_collection: str = "sentinel-2-l2a"
    static_catalog_manifest_path: str = "/data/demo/manifest.json"
    static_catalog_mount_path: str = "/data/demo"

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

    # Tiler. SEC-01: the tiler requires this exact shared token on every
    # request (X-Tiler-Token header) — apps/api attaches it when building
    # tile URLs for the frontend (see app/routers/*.py's tilejson helpers),
    # services/tiler validates it (see services/tiler/app/security.py). Not
    # a substitute for the SSRF allowlist, just a second gate: without it, a
    # request that somehow reaches the tiler directly (bypassing the SPA)
    # can't use it as an open proxy even for allowlisted hosts.
    tiler_base_url: str = "http://localhost:8001"
    tiler_public_base_url: str = "http://localhost:8001"
    tiler_token: str = "change-me-dev-tiler-token"

    # Inference (placeholder detection). SEC-09: shared secret, same pattern
    # as tiler_token — see services/inference/app/security.py.
    inference_base_url: str = "http://localhost:8002"
    inference_token: str = "change-me-dev-inference-token"

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

    @model_validator(mode="after")
    def _refuse_weak_production_secrets(self) -> "Settings":
        """SEC-04: a production boot with a known-default or short secret is
        not a warning, it's a refusal to start — this is the one thing
        standing between "someone forgot to run the secret generator" and a
        deployment that's silently using a password anyone can read out of
        this repo's own git history. Never triggers in development, where
        the whole point is that infra/.env.example's placeholders just work."""
        if self.vantage_env != "production":
            return self

        def _weak(value: str) -> bool:
            return value in _KNOWN_DEFAULT_SECRETS or len(value) < _MIN_PRODUCTION_SECRET_LENGTH

        offenders: list[str] = []
        if _weak(self.jwt_secret):
            offenders.append("JWT_SECRET")
        if _weak(self.s3_secret_access_key):
            offenders.append("S3_SECRET_ACCESS_KEY")
        if _weak(self.tiler_token):
            offenders.append("TILER_TOKEN")
        if _weak(self.inference_token):
            offenders.append("INFERENCE_TOKEN")

        db_password = urlparse(self.database_url).password or ""
        if _weak(db_password):
            offenders.append("DATABASE_URL's password")

        if offenders:
            raise ValueError(
                "VANTAGE_ENV=production but refusing to boot with a default or "
                f"too-short secret: {', '.join(offenders)}. Run the secret generator "
                "(scripts/generate_dev_secrets.py for dev, or the launcher's first-run "
                "flow for the packaged app) before setting VANTAGE_ENV=production."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
