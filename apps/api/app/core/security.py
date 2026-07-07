import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.schemas.auth import UserClaims

logger = logging.getLogger(__name__)

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/dev-token")


def create_dev_token() -> tuple[str, int]:
    # PLACEHOLDER(v1): single dev user, identity env-driven (DEV_USER_SUB/NAME/
    # ROLES) rather than a code literal, shaped like real OIDC claims so
    # swapping to a real IdP later only changes how the token is issued/
    # verified, not the shape callers depend on. Logged loudly every issuance
    # so this never gets mistaken for a real auth path in server logs.
    logger.warning(
        "issuing PLACEHOLDER dev-only JWT for %r — this is not production auth",
        settings.dev_user_sub,
    )
    now = datetime.now(timezone.utc)
    expires_in = settings.jwt_expire_minutes * 60
    payload = {
        "sub": settings.dev_user_sub,
        "name": settings.dev_user_name,
        "roles": settings.dev_user_roles,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def get_current_user(token: str = Depends(_oauth2_scheme)) -> UserClaims:
    # TODO(v2): swap HS256 shared-secret verification for RS256 + JWKS fetched
    # from the self-hosted Keycloak issuer. This function's signature and
    # return type stay the same; only the verification body changes.
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return UserClaims(sub=payload["sub"], name=payload["name"], roles=payload["roles"])
