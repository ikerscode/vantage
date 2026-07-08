"""Real regression coverage for the SSRF hardening in app/security.py
(BRIEF v1.4 SEC-01) — the accept-check payloads (metadata IP, file://,
private IP, missing token) were verified manually against the live tiler
during v1.4's development (see SECURITY_FIXES_REPORT.md); this makes the
same payloads a repeatable CI test instead of a one-off manual check."""

import socket

import pytest
from fastapi import HTTPException

from app import security


def test_file_scheme_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        security.validated_url("file:///etc/passwd")
    assert exc_info.value.status_code == 400
    assert "scheme" in exc_info.value.detail


def test_ftp_scheme_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        security.validated_url("ftp://example.com/file.tif")
    assert exc_info.value.status_code == 400


def test_host_not_on_the_allowlist_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        security.validated_url("http://169.254.169.254/latest/meta-data/")
    assert exc_info.value.status_code == 400
    assert "allowlist" in exc_info.value.detail


def test_allowlisted_host_that_resolves_to_a_private_ip_is_rejected(monkeypatch):
    # Simulates DNS rebinding: a hostname that IS on the allowlist but
    # resolves (at request time) to a private address — the allowlist check
    # alone can't catch this, only the DNS-resolution step can.
    monkeypatch.setattr(security, "_allowed_hosts", lambda: {"rebound.example.com"})
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: [(socket.AF_INET, None, None, None, ("10.0.0.1", 0))]
    )
    with pytest.raises(HTTPException) as exc_info:
        security.validated_url("http://rebound.example.com/scene.tif")
    assert exc_info.value.status_code == 400
    assert "disallowed address" in exc_info.value.detail


def test_allowlisted_host_with_a_real_public_ip_is_accepted(monkeypatch):
    monkeypatch.setattr(security, "_allowed_hosts", lambda: {"earth-search.aws.element84.com"})
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: [(socket.AF_INET, None, None, None, ("52.1.2.3", 0))]
    )
    url = "http://earth-search.aws.element84.com/v1/collections"
    assert security.validated_url(url) == url


def test_s3_url_for_the_configured_bucket_is_accepted(monkeypatch):
    monkeypatch.setattr(security, "_own_bucket", lambda: "vantage-analysis")
    url = "s3://vantage-analysis/analyses/abc123.tif"
    assert security.validated_url(url) == url


def test_s3_url_for_a_different_bucket_is_rejected(monkeypatch):
    monkeypatch.setattr(security, "_own_bucket", lambda: "vantage-analysis")
    with pytest.raises(HTTPException) as exc_info:
        security.validated_url("s3://someone-elses-bucket/secrets.tif")
    assert exc_info.value.status_code == 400


def test_missing_token_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        security.require_tiler_token(x_tiler_token=None)
    assert exc_info.value.status_code == 401


def test_wrong_token_is_rejected(monkeypatch):
    monkeypatch.setenv("TILER_TOKEN", "the-real-token")
    with pytest.raises(HTTPException) as exc_info:
        security.require_tiler_token(x_tiler_token="a-guessed-token")
    assert exc_info.value.status_code == 401


def test_correct_token_is_accepted(monkeypatch):
    monkeypatch.setenv("TILER_TOKEN", "the-real-token")
    security.require_tiler_token(x_tiler_token="the-real-token")  # does not raise
