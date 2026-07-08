"""Real regression coverage for Settings._refuse_weak_production_secrets
(BRIEF v1.4 SEC-04) — the fail-closed boot check was verified manually
during v1.4's development (see SECURITY_FIXES_REPORT.md); this makes that
verification a real, repeatable, CI-run test instead of a one-off manual
check that could silently regress."""

import secrets

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _real_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def test_development_boots_with_the_known_dev_defaults():
    # The whole point of "development" mode: infra/.env.example's
    # changeme-* placeholders must keep working with zero setup.
    settings = Settings(_env_file=None, vantage_env="development")
    assert settings.jwt_secret == "change-me-dev-secret"


def test_production_refuses_to_boot_with_any_default_secret():
    with pytest.raises(ValidationError, match="refusing to boot"):
        Settings(_env_file=None, vantage_env="production")


def test_production_refuses_a_too_short_real_looking_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, vantage_env="production", jwt_secret="short", tiler_token=_real_secret(48))


def test_production_boots_cleanly_with_real_generated_secrets():
    settings = Settings(
        _env_file=None,
        vantage_env="production",
        jwt_secret=_real_secret(48),
        s3_secret_access_key=_real_secret(32),
        tiler_token=_real_secret(48),
        inference_token=_real_secret(48),
        database_url=f"postgresql+psycopg://vantage_app:{_real_secret(32)}@db:5432/vantage",
    )
    assert settings.vantage_env == "production"


def test_production_error_names_every_weak_secret_at_once():
    # A single refusal that lists every offender is more useful to an
    # operator than failing one field at a time across repeated boots.
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, vantage_env="production", tiler_token=_real_secret(48))
    message = str(exc_info.value)
    assert "JWT_SECRET" in message
    assert "S3_SECRET_ACCESS_KEY" in message
    assert "TILER_TOKEN" not in message  # this one was given a real secret
