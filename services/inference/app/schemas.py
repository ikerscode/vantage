from pydantic import BaseModel


class DetectRequest(BaseModel):
    # One entry per chip, PNG bytes, base64-encoded. A single batched request
    # (not one request per chip) so the model backend can run one batched
    # forward pass through the network instead of N sequential ones — see
    # ModelBackend.predict_batch. apps/api's detection_pipeline.py sends every
    # chip for an analysis (up to MAX_CHIPS) in one call.
    images_base64: list[str]


class DetectionBox(BaseModel):
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in chip pixel coordinates
    score: float
    label: str


class DetectResponse(BaseModel):
    # One entry per input image, same order as the request's images_base64.
    detections: list[list[DetectionBox]]
