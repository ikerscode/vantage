from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import settings
from app.core.security import create_dev_token, get_current_user
from app.schemas.auth import TokenResponse, UserClaims

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else None) or ""
    return host in ("127.0.0.1", "::1", "localhost")


@router.post("/dev-token", response_model=TokenResponse)
def issue_dev_token(request: Request) -> TokenResponse:
    """PLACEHOLDER(v1): issues a token for the single hardcoded dev user, no
    credential check. v2 replaces this with a real OIDC code-exchange against
    self-hosted Keycloak; get_current_user's shape doesn't need to change.

    SEC-02: this endpoint hands out a valid token to anyone who can reach
    it, no password. Two fail-closed gates: disabled entirely in production
    (VANTAGE_ENV=production is only set on deployments where this stub has
    no business existing at all — see COMPLIANCE.md's single-user note),
    and loopback-only even in development (rate-limiting is a documented
    follow-up — see SECURITY_FIXES_REPORT.md).
    """
    if settings.vantage_env == "production":
        raise HTTPException(status_code=404, detail="not found")
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="dev-token is only issued to loopback clients")
    token, expires_in = create_dev_token()
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/tiler-token")
def get_tiler_token(_user: UserClaims = Depends(get_current_user)) -> dict:
    """SEC-01: the frontend fetches this once (after acquiring its own JWT)
    and attaches it as an X-Tiler-Token header on every tile request via
    MapLibre's transformRequest — see apps/web/src/components/MapCanvas.tsx.
    Requires the same auth as everything else here, so a caller needs a
    valid session before they can even learn the tiler's shared secret."""
    return {"tilerToken": settings.tiler_token}
