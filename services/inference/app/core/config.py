from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    device: str = "cpu"  # "cpu" | "cuda" — GPU-ready, CPU default per CLAUDE.md
    # "torchvision_fasterrcnn" (default): COCO-pretrained placeholder, generic
    # classes, proves the pipeline. "torchvision_fasterrcnn_vessel" (BRIEF
    # v1.8, opt-in): fine-tuned on real Sentinel-2 vessel annotations — see
    # VESSEL_DETECTION_REPORT.md for the honest accuracy/limitations story.
    model_backend: str = "torchvision_fasterrcnn"
    vessel_weights_path: str = "/app/weights/vessel_fasterrcnn.pth"
    score_threshold: float = 0.5

    # SEC-09
    inference_token: str = "change-me-dev-inference-token"
    # Chips are tiled at 512x512 by apps/api's detection_pipeline.py — 4M
    # pixels (2000x2000) is generous headroom over that, while still
    # rejecting a decompression-bomb-style payload (PIL's own default,
    # ~178M pixels, is calibrated for "don't OOM on a legitimate huge photo",
    # not for "this service only ever expects small fixed-size chips"). This
    # is checked per-image even in a batched /detect request (see
    # schemas.DetectRequest), not once for the whole payload.
    max_image_pixels: int = 4_000_000
    # /detect now takes a whole batch of chips in one request (up to
    # MAX_CHIPS=9 in apps/api's detection_pipeline.py), not one chip per
    # request. Worst case: 9 chips x 512x512x3 raw bytes (~786KB each) x
    # ~1.33 for base64 ~= 9.5MB -- 20MB keeps more than 2x headroom over that
    # without needing to grow alongside MAX_CHIPS/CHIP_SIZE for now.
    max_body_bytes: int = 20_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
