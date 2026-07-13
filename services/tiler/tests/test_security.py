"""Real regression coverage for the SSRF hardening in app/security.py
(BRIEF v1.4 SEC-01) — the accept-check payloads (metadata IP, file://,
private IP, missing token) were verified manually against the live tiler
during v1.4's development (see SECURITY_FIXES_REPORT.md); this makes the
same payloads a repeatable CI test instead of a one-off manual check."""

import socket
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import security


@pytest.fixture(autouse=True)
def _clear_dns_cache():
    """The DNS-resolution cache (app.security._dns_cache) is module-level and
    would otherwise leak resolved IPs between tests that reuse a hostname —
    reset it before every test so each one resolves fresh, same as if caching
    were off."""
    security._dns_cache.clear()
    yield
    security._dns_cache.clear()


def test_file_scheme_outside_the_static_catalog_mount_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        security.validated_url("file:///etc/passwd")
    assert exc_info.value.status_code == 400
    assert "only allowed under" in exc_info.value.detail


def test_file_scheme_path_traversal_out_of_the_mount_is_rejected(tmp_path, monkeypatch):
    # "/mount/../secret" starts with "/mount" as raw text but must not be
    # allowed through — this is exactly what a naive string-prefix check
    # would miss.
    mount = tmp_path / "mount"
    mount.mkdir()
    secret = tmp_path / "secret.tif"
    secret.write_text("not real imagery")
    monkeypatch.setattr(security, "_static_catalog_mount_path", lambda: str(mount))

    with pytest.raises(HTTPException) as exc_info:
        security.validated_url(f"file://{mount}/../secret.tif")
    assert exc_info.value.status_code == 400
    assert "only allowed under" in exc_info.value.detail


def test_file_scheme_under_the_static_catalog_mount_is_accepted(tmp_path, monkeypatch):
    mount = tmp_path / "mount"
    (mount / "2025-11-01").mkdir(parents=True)
    scene = mount / "2025-11-01" / "visual.tif"
    scene.write_text("not real imagery")
    monkeypatch.setattr(security, "_static_catalog_mount_path", lambda: str(mount))

    # GDAL/rasterio want a bare path back, not a file:// URI.
    assert security.validated_url(f"file://{scene}") == str(scene.resolve())


def test_file_scheme_for_the_mount_root_itself_is_accepted(tmp_path, monkeypatch):
    mount = tmp_path / "mount"
    mount.mkdir()
    monkeypatch.setattr(security, "_static_catalog_mount_path", lambda: str(mount))

    assert security.validated_url(f"file://{mount}") == str(Path(mount).resolve())


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


def test_dns_cache_skips_a_second_real_lookup_within_ttl(monkeypatch):
    calls = []

    def fake_getaddrinfo(host, port):
        calls.append(host)
        return [(socket.AF_INET, None, None, None, ("52.1.2.3", 0))]

    monkeypatch.setattr(security, "_allowed_hosts", lambda: {"earth-search.aws.element84.com"})
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    url = "http://earth-search.aws.element84.com/v1/collections"
    security.validated_url(url)
    security.validated_url(url)
    security.validated_url(url)

    # Three requests to the same host, one real DNS round-trip — this is the
    # whole point: a single viewport pan fires many tile requests to the same
    # 1-2 allowlisted hosts, and only the first should ever hit the network.
    assert calls == ["earth-search.aws.element84.com"]


def test_dns_cache_still_catches_rebinding_on_a_cached_hit(monkeypatch):
    # The cache must never be allowed to paper over a genuine rebinding — if
    # the (cached) resolution is a disallowed address, it's still rejected.
    monkeypatch.setattr(security, "_allowed_hosts", lambda: {"rebound.example.com"})
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: [(socket.AF_INET, None, None, None, ("10.0.0.1", 0))]
    )
    url = "http://rebound.example.com/scene.tif"

    with pytest.raises(HTTPException):
        security.validated_url(url)
    # Second call hits the cache (same fake resolver would raise if called
    # again anyway, since it always returns the same private IP) — still rejected.
    with pytest.raises(HTTPException):
        security.validated_url(url)


def test_dns_cache_re_resolves_after_ttl_expiry(monkeypatch):
    calls = []

    def fake_getaddrinfo(host, port):
        calls.append(host)
        return [(socket.AF_INET, None, None, None, ("52.1.2.3", 0))]

    monkeypatch.setattr(security, "_allowed_hosts", lambda: {"earth-search.aws.element84.com"})
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    fake_now = [1000.0]
    monkeypatch.setattr(security.time, "monotonic", lambda: fake_now[0])
    monkeypatch.setattr(security, "_DNS_CACHE_TTL_S", 30.0)

    url = "http://earth-search.aws.element84.com/v1/collections"
    security.validated_url(url)
    fake_now[0] += 31  # past the 30s TTL
    security.validated_url(url)

    assert calls == ["earth-search.aws.element84.com", "earth-search.aws.element84.com"]


def test_dns_cache_disabled_when_ttl_is_zero(monkeypatch):
    calls = []

    def fake_getaddrinfo(host, port):
        calls.append(host)
        return [(socket.AF_INET, None, None, None, ("52.1.2.3", 0))]

    monkeypatch.setattr(security, "_allowed_hosts", lambda: {"earth-search.aws.element84.com"})
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(security, "_DNS_CACHE_TTL_S", 0.0)

    url = "http://earth-search.aws.element84.com/v1/collections"
    security.validated_url(url)
    security.validated_url(url)

    assert calls == ["earth-search.aws.element84.com", "earth-search.aws.element84.com"]


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
