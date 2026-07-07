from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    device: str = "cpu"  # "cpu" | "cuda" — GPU-ready, CPU default per CLAUDE.md
    model_backend: str = "torchvision_fasterrcnn"
    score_threshold: float = 0.5


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
