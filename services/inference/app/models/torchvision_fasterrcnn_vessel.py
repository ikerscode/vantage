from pathlib import Path

import torch
from PIL import Image
from torchvision.models.detection import fasterrcnn_resnet50_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.transforms.functional import to_tensor

from app.core.config import settings
from app.models.base import ModelBackend
from app.schemas import DetectionBox

# Class index 0 is background (torchvision detection convention); this
# backend was fine-tuned for a single foreground class.
_CATEGORIES = {1: "vessel"}


class TorchvisionFasterRCNNVessel(ModelBackend):
    """Fine-tuned variant of the same locked-in architecture (CLAUDE.md
    §4: fasterrcnn_resnet50_fpn, BSD-3) — same class as
    TorchvisionFasterRCNN, but with its box_predictor head replaced and
    fine-tuned for 2 classes (background/vessel) on real, held-out-tested
    Sentinel-2 imagery (BRIEF v1.8; see VESSEL_DETECTION_REPORT.md for the
    dataset, training run, and honest accuracy/limitations). This is a
    genuinely valid detection task at Sentinel-2's ~10m/px resolution
    (mean annotated vessel size ~9px) — unlike xView-style small-object
    classes, which BRIEF v1.8's own research ruled out as resolution-
    mismatched at this GSD. The COCO-pretrained TorchvisionFasterRCNN
    backend remains the default (see factory.py) — this is an opt-in,
    clearly-labeled alternative, not a replacement."""

    def __init__(self) -> None:
        weights_path = Path(settings.vessel_weights_path)
        if not weights_path.is_file():
            raise FileNotFoundError(
                f"MODEL_BACKEND=torchvision_fasterrcnn_vessel was selected but no weights "
                f"file exists at {weights_path} — this is a gitignored local/build artifact "
                f"(165.7MB), not something silently faked. See "
                f"services/inference/weights/README.md to produce it, or switch back to "
                f"MODEL_BACKEND=torchvision_fasterrcnn (the COCO placeholder, default)."
            )

        self._model = fasterrcnn_resnet50_fpn(weights=None, weights_backbone=None)
        in_features = self._model.roi_heads.box_predictor.cls_score.in_features
        self._model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes=2)

        # weights_only=True (SEC, BRIEF v1.9): this checkpoint is a plain
        # state_dict of tensors, so this is functionally invisible (verified:
        # identical eval F1 before/after — see VESSEL_DETECTION_REPORT.md),
        # but it refuses to run the arbitrary-code pickle path during
        # deserialization. That matters more now that weights can travel via
        # a container registry (BRIEF v1.7 thin-install) rather than only
        # ever being this project's own local training output.
        state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
        self._model.load_state_dict(state_dict)
        self._model.eval()
        self._model.to(settings.device)

    @torch.inference_mode()
    def predict_batch(self, images: list[Image.Image]) -> list[list[DetectionBox]]:
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
                    DetectionBox(box=tuple(box), score=score, label=_CATEGORIES.get(label, "unknown"))
                )
            results.append(detections)
        return results
