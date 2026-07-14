"""Real regression coverage for the /detect router's batching contract
(PERF: this used to be one image in, one detection list out; it's now a
list of images in, one detection list PER image out, in order -- see
app.models.base.ModelBackend.predict_batch and
apps/api/app/services/detection_pipeline.py's caller). A fake ModelBackend
stands in for the real torchvision model here -- this is testing the
router's plumbing (base64 decode, ordering, empty-batch handling), not the
model's own detection accuracy, which needs real weights (see
VESSEL_DETECTION_REPORT.md for that verification)."""

import base64
import io

from PIL import Image

from app.routers import detect as detect_router
from app.schemas import DetectionBox, DetectRequest


class FakeModelBackend:
    def __init__(self, results: list[list[DetectionBox]]):
        self._results = results
        self.seen_batch_size: int | None = None

    def predict_batch(self, images):
        self.seen_batch_size = len(images)
        return self._results


def _png_base64(size=(4, 4)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_detect_returns_one_detection_list_per_image_in_order(monkeypatch):
    fake_backend = FakeModelBackend(
        [
            [DetectionBox(box=(0, 0, 1, 1), score=0.9, label="a")],
            [],
            [DetectionBox(box=(2, 2, 3, 3), score=0.5, label="b")],
        ]
    )
    monkeypatch.setattr(detect_router, "get_model_backend", lambda: fake_backend)

    payload = DetectRequest(images_base64=[_png_base64(), _png_base64(), _png_base64()])
    response = detect_router.detect(payload)

    assert fake_backend.seen_batch_size == 3
    assert len(response.detections) == 3
    assert response.detections[0][0].label == "a"
    assert response.detections[1] == []
    assert response.detections[2][0].label == "b"


def test_detect_handles_an_empty_batch(monkeypatch):
    class EmptyBatchBackend:
        def predict_batch(self, images):
            assert images == []
            return []

    # Directly exercises the same empty-list path apps/api's detection_pipeline
    # takes when an AOI's scene read produces zero chips.
    monkeypatch.setattr(detect_router, "get_model_backend", lambda: EmptyBatchBackend())

    response = detect_router.detect(DetectRequest(images_base64=[]))

    assert response.detections == []
