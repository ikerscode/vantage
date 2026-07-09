from functools import lru_cache

from app.core.config import settings
from app.models.base import ModelBackend
from app.models.torchvision_fasterrcnn import TorchvisionFasterRCNN
from app.models.torchvision_fasterrcnn_vessel import TorchvisionFasterRCNNVessel


@lru_cache
def get_model_backend() -> ModelBackend:
    if settings.model_backend == "torchvision_fasterrcnn":
        return TorchvisionFasterRCNN()
    if settings.model_backend == "torchvision_fasterrcnn_vessel":
        return TorchvisionFasterRCNNVessel()
    raise ValueError(f"unknown MODEL_BACKEND: {settings.model_backend!r}")
