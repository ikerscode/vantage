from fastapi import APIRouter

from app.core.security import create_dev_token
from app.schemas.auth import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/dev-token", response_model=TokenResponse)
def issue_dev_token() -> TokenResponse:
    """PLACEHOLDER(v1): issues a token for the single hardcoded dev user, no
    credential check. v2 replaces this with a real OIDC code-exchange against
    self-hosted Keycloak; get_current_user's shape doesn't need to change."""
    token, expires_in = create_dev_token()
    return TokenResponse(access_token=token, expires_in=expires_in)
