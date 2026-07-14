from abc import ABC, abstractmethod

from PIL import Image

from app.schemas import DetectionBox


class ModelBackend(ABC):
    """Swappable detector interface (CLAUDE.md: "ModelBackend interface, CPU
    default / GPU-ready"). TorchvisionFasterRCNN is the only concrete v1 impl.

    predict_batch takes a list so a caller with multiple chips (apps/api's
    detection_pipeline.py tiles an AOI into up to MAX_CHIPS chips) sends them
    as one batched forward pass instead of one request per chip — a real
    throughput win on GPU (kernel-launch/memory-transfer overhead amortizes
    across the batch) and a real latency win even on CPU (one round trip
    instead of N)."""

    @abstractmethod
    def predict_batch(self, images: list[Image.Image]) -> list[list[DetectionBox]]: ...
