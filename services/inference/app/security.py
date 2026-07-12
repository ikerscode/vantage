"""SEC-09: this service decodes and runs a CNN over arbitrary
caller-supplied image bytes — a shared-token check (mirroring
services/tiler/app/security.py's require_tiler_token) means only apps/api
can reach it, not anyone who happens to find the port."""

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException


def require_inference_token(x_inference_token: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("INFERENCE_TOKEN", "change-me-dev-inference-token")
    # Constant-time compare (see services/tiler/app/security.py for why a plain
    # `!=` is a timing side-channel on the shared secret).
    if x_inference_token is None or not hmac.compare_digest(
        x_inference_token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="missing or invalid X-Inference-Token header")
