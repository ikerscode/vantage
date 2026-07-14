import base64
import io
import threading

from fastapi import APIRouter
from PIL import Image

from app.models.factory import get_model_backend
from app.schemas import DetectRequest, DetectResponse

router = APIRouter(tags=["detect"])

# PERF/stability: this route is a plain `def`, so FastAPI/Starlette runs it in
# a worker thread pool, not on the event loop -- meaning two concurrent
# /detect requests (e.g. an on-demand analysis and a monitor sweep's
# auto-detection, or two analysts working at once) can genuinely call
# predict_batch on two different threads AT THE SAME TIME against the same
# model/GPU. On a small GPU (the reference deployment target is a 6GB
# laptop card, not a datacenter one) two concurrent batches' worth of
# activation memory can plausibly exceed available VRAM and OOM, where
# running them one after another comfortably fits. This lock trades a small
# amount of queuing latency under real concurrent load for never letting
# peak GPU/CPU memory usage exceed one batch's worth, regardless of how many
# requests arrive at once.
_inference_lock = threading.Lock()


@router.post("/detect", response_model=DetectResponse)
def detect(payload: DetectRequest) -> DetectResponse:
    images = [Image.open(io.BytesIO(base64.b64decode(b))) for b in payload.images_base64]
    with _inference_lock:
        detections = get_model_backend().predict_batch(images)
    return DetectResponse(detections=detections)
