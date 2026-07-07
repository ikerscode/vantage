"""SEC-01: the tiler is a generic "fetch and render whatever URL you give
me" service — that's exactly the shape of an SSRF-as-a-service if the `url`
query param isn't restricted. Two independent gates, both required:

  1. `validated_url` (a titiler `path_dependency`): host allowlist (env-
     driven) + DNS resolution of every candidate IP, rejecting private/
     loopback/link-local/reserved/multicast/unspecified addresses, on top
     of a scheme check. This is the actual SSRF fix — allowlisting by
     hostname alone is not enough because DNS rebinding lets an attacker
     register a public hostname that later resolves to 169.254.169.254 or
     10.0.0.1; every request re-resolves and re-checks.
  2. `require_tiler_token` (a plain header check): even an allowlisted host
     can only be reached by a caller holding the per-install shared secret,
     so the tiler isn't a bare anonymous open proxy for the allowlisted
     hosts either.

`s3://` URLs are a deliberate, narrow exception to the http(s)-only rule:
the app's own change-detection outputs are tiled via `url=s3://<bucket>/...`
(see apps/api/app/services/change_detection_pipeline.py + GDAL's own
AWS_* env-configured credentials) and that's the ONE legitimate non-http(s)
case — restricted to the app's own configured bucket, never an arbitrary
bucket name a caller could supply to read something else out of the same
MinIO/S3 account.
"""

import ipaddress
import os
import socket
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Query

_DISALLOWED_IP_PREDICATES = (
    "is_private",
    "is_loopback",
    "is_link_local",
    "is_reserved",
    "is_multicast",
    "is_unspecified",
)


def _allowed_hosts() -> set[str]:
    raw = os.environ.get(
        "TILER_ALLOWED_HOSTS",
        "earth-search.aws.element84.com,sentinel-cogs.s3.us-west-2.amazonaws.com",
    )
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _own_bucket() -> str:
    return os.environ.get("S3_BUCKET_ANALYSIS", "vantage-analysis")


def _reject_if_disallowed_ip(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail=f"could not resolve host: {hostname}") from exc

    for _family, _type, _proto, _canonname, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if any(getattr(ip, predicate) for predicate in _DISALLOWED_IP_PREDICATES):
            raise HTTPException(
                status_code=400,
                detail=f"host {hostname!r} resolves to a disallowed address ({ip}) — "
                "cloud metadata, loopback, and private/reserved ranges are never tileable",
            )


def validated_url(url: Annotated[str, Query(description="Dataset URL")]) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme == "s3":
        # netloc is exactly the bucket name for s3://bucket/key URLs.
        if parsed.netloc != _own_bucket():
            raise HTTPException(
                status_code=400,
                detail="s3:// URLs are only allowed for this app's own analysis-output bucket",
            )
        return url

    if scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail=f"unsupported URL scheme: {scheme!r}")

    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL has no hostname")

    hostname = parsed.hostname.lower()
    if hostname not in _allowed_hosts():
        raise HTTPException(
            status_code=400,
            detail=f"host {hostname!r} is not in the imagery source allowlist "
            "(set TILER_ALLOWED_HOSTS to add it)",
        )

    _reject_if_disallowed_ip(hostname)
    return url


def require_tiler_token(x_tiler_token: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("TILER_TOKEN", "change-me-dev-tiler-token")
    if x_tiler_token != expected:
        raise HTTPException(status_code=401, detail="missing or invalid X-Tiler-Token header")
