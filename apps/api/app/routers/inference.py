import httpx
from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.security import get_current_user
from app.schemas.auth import UserClaims
from app.schemas.inference import InferenceStatus

router = APIRouter(prefix="/inference", tags=["inference"])

# A UI readiness probe, not a data request — it must come back fast enough to
# never visibly stall the Layers panel, and "slow" is close enough to "down"
# for what this answers.
STATUS_TIMEOUT_S = 2.0


@router.get("/status", response_model=InferenceStatus)
def inference_status(_user: UserClaims = Depends(get_current_user)) -> InferenceStatus:
    """Live-proxied from the inference service's own /health rather than read
    from this process's env: MODEL_BACKEND is the inference container's
    setting, and while the compose stack feeds both containers one .env, a
    split deployment can point INFERENCE_BASE_URL anywhere — reporting what
    the service SAYS it's running can't drift from what /detect will actually
    do, and "unreachable" falls out as an honest first-class answer instead
    of a guess (CLAUDE.md §3). Found live: the UI hardcoded the COCO-
    placeholder description and kept showing it after the backend had been
    switched to the fine-tuned vessel detector."""
    try:
        response = httpx.get(f"{settings.inference_base_url}/health", timeout=STATUS_TIMEOUT_S)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return InferenceStatus(reachable=False)
    return InferenceStatus(
        reachable=True,
        model_backend=payload.get("model_backend"),
        device=payload.get("device"),
    )
