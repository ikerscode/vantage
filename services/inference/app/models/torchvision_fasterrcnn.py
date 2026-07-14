import torch
from PIL import Image
from torchvision.models.detection import (
    FasterRCNN_ResNet50_FPN_Weights,
    fasterrcnn_resnet50_fpn,
)
from torchvision.transforms.functional import to_tensor

from app.core.config import settings
from app.models.base import ModelBackend
from app.schemas import DetectionBox


class TorchvisionFasterRCNN(ModelBackend):
    """COCO-pretrained torchvision detector (BSD-3-licensed). Generic object
    classes, not satellite-specific — this is the "placeholder" in
    "placeholder detection"; real overhead-imagery training data (xView etc.)
    is non-commercial-licensed and deliberately not bundled here."""

    def __init__(self) -> None:
        self._weights = FasterRCNN_ResNet50_FPN_Weights.DEFAULT
        self._categories = self._weights.meta["categories"]
        self._model = fasterrcnn_resnet50_fpn(weights=self._weights)
        self._model.eval()
        self._model.to(settings.device)

    @torch.inference_mode()
    def predict_batch(self, images: list[Image.Image]) -> list[list[DetectionBox]]:
        # torchvision detection models natively accept a list of tensors of
        # different sizes in one forward pass (their internal transform pads/
        # batches them) — one real batched call, not a Python-level loop
        # hiding N model calls.
        tensors = [to_tensor(image.convert("RGB")).to(settings.device) for image in images]
        outputs = self._model(tensors) if tensors else []

        results = []
        for output in outputs:
            detections = []
            for box, score, label in zip(
                output["boxes"].tolist(), output["scores"].tolist(), output["labels"].tolist()
            ):
                if score < settings.score_threshold:
                    continue
                detections.append(
                    DetectionBox(box=tuple(box), score=score, label=self._categories[label])
                )
            results.append(detections)
        return results
