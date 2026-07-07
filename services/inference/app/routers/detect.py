import base64
import io

from fastapi import APIRouter
from PIL import Image

from app.models.factory import get_model_backend
from app.schemas import DetectRequest, DetectResponse

router = APIRouter(tags=["detect"])


@router.post("/detect", response_model=DetectResponse)
def detect(payload: DetectRequest) -> DetectResponse:
    image = Image.open(io.BytesIO(base64.b64decode(payload.image_base64)))
    detections = get_model_backend().predict(image)
    return DetectResponse(detections=detections)
