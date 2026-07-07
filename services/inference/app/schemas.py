from pydantic import BaseModel


class DetectRequest(BaseModel):
    image_base64: str  # PNG bytes, base64-encoded


class DetectionBox(BaseModel):
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in chip pixel coordinates
    score: float
    label: str


class DetectResponse(BaseModel):
    detections: list[DetectionBox]
