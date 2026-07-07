from fastapi import Depends, FastAPI, HTTPException, Request
from PIL import Image

from app.core.config import settings
from app.routers import detect, health
from app.security import require_inference_token

# SEC-09: PIL's own default (~178M pixels) is calibrated for "don't OOM on a
# legitimate huge photo" — this service only ever expects small, fixed-size
# chips (see Settings.max_image_pixels's comment), so a much tighter cap
# rejects a decompression-bomb-style payload outright instead of trying to
# allocate for it.
Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

app = FastAPI(title="VANTAGE Inference")


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="request body too large")
    return await call_next(request)


app.include_router(health.router)
app.include_router(detect.router, dependencies=[Depends(require_inference_token)])
