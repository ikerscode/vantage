import socket
import struct

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import settings
from app.core.security import create_dev_token, get_current_user
from app.schemas.auth import TokenResponse, UserClaims

router = APIRouter(prefix="/auth", tags=["auth"])


def _container_default_gateway() -> str | None:
    """The address Docker's NAT makes a host-loopback client look like it's
    coming from, from inside this container — found for real in CI (BRIEF
    v1.5): a host process hitting the published port at 127.0.0.1 never
    reaches uvicorn as 127.0.0.1, because Docker's port-publish path
    masquerades it as the bridge gateway address (real loopback doesn't
    survive the NAT hop). Native/non-container dev never exercised this.
    A sibling container calling api:8000 directly over the compose network
    presents its OWN container IP here, not the gateway's, so keying on
    this exact address (not the whole bridge subnet) doesn't widen the gate
    to other containers — only to "the host, via its published port."
    """
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if fields[1] == "00000000":  # destination 0.0.0.0 == default route
                    return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    except (FileNotFoundError, IndexError, ValueError):
        return None
    return None


def _is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else None) or ""
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    return host != "" and host == _container_default_gateway()


@router.post("/dev-token", response_model=TokenResponse)
def issue_dev_token(request: Request) -> TokenResponse:
    """PLACEHOLDER(v1): issues a token for the single hardcoded dev user, no
    credential check. v2 replaces this with a real OIDC code-exchange against
    self-hosted Keycloak; get_current_user's shape doesn't need to change.

    SEC-02: this endpoint hands out a valid token to anyone who can reach
    it, no password — loopback-only is the one fail-closed gate, in every
    environment including production (rate-limiting is a documented
    follow-up — see SECURITY_FIXES_REPORT.md).

    Found for real in CI (BRIEF v1.6): this used to also 404 unconditionally
    when VANTAGE_ENV=production, envisioning a hypothetical shared/hosted
    deployment where this stub has no business existing. But the packaged
    single-user desktop app *also* sets VANTAGE_ENV=production
    (infra/.env.prod.template) and has no other auth mechanism yet — v2's
    real OIDC/Keycloak integration doesn't exist — so that blanket
    production disablement silently broke the packaged app's own dev-token
    bootstrap (apps/web/src/api/auth.ts's fetchDevToken has no fallback),
    never caught before because nobody had run the packaged app end-to-end
    until this brief's acceptance test. docs/AIRGAP.md and COMPLIANCE.md
    already document the desktop app as relying on exactly this stub — the
    loopback gate alone is what actually matches that design (every
    real-deployment app-owned service is loopback-bound already, per SEC-03
    / docker-compose.prod.yml), so it's the only gate needed, in every env.
    """
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
