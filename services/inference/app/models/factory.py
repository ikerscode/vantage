from functools import lru_cache

from app.core.config import settings
from app.models.base import ModelBackend
from app.models.torchvision_fasterrcnn import TorchvisionFasterRCNN


@lru_cache
def get_model_backend() -> ModelBackend:
    if settings.model_backend == "torchvision_fasterrcnn":
        return TorchvisionFasterRCNN()
    raise ValueError(f"unknown MODEL_BACKEND: {settings.model_backend!r}")
