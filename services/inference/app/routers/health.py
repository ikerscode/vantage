from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    # model_backend/device let the API (and through it, the UI) report which
    # detector is ACTUALLY serving /detect, instead of anyone hardcoding an
    # assumption about it (CLAUDE.md §3, honest seams — found live: the UI
    # kept describing the COCO placeholder after this service had been
    # switched to the vessel backend). Deliberately on the un-tokened health
    # route: it names a model architecture, not a secret, and the API's
    # proxy (apps/api/app/routers/inference.py) is what the frontend reads.
    return {
        "status": "ok",
        "model_backend": settings.model_backend,
        "device": settings.device,
    }
