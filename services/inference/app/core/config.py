from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    device: str = "cpu"  # "cpu" | "cuda" — GPU-ready, CPU default per CLAUDE.md
    model_backend: str = "torchvision_fasterrcnn"
    score_threshold: float = 0.5

    # SEC-09
    inference_token: str = "change-me-dev-inference-token"
    # Chips are tiled at 512x512 by apps/api's detection_pipeline.py — 4M
    # pixels (2000x2000) is generous headroom over that, while still
    # rejecting a decompression-bomb-style payload (PIL's own default,
    # ~178M pixels, is calibrated for "don't OOM on a legitimate huge photo",
    # not for "this service only ever expects small fixed-size chips").
    max_image_pixels: int = 4_000_000
    max_body_bytes: int = 20_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
