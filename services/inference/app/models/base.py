from abc import ABC, abstractmethod

from PIL import Image

from app.schemas import DetectionBox


class ModelBackend(ABC):
    """Swappable detector interface (CLAUDE.md: "ModelBackend interface, CPU
    default / GPU-ready"). TorchvisionFasterRCNN is the only concrete v1 impl."""

    @abstractmethod
    def predict(self, image: Image.Image) -> list[DetectionBox]: ...
