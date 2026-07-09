"""Real regression coverage for the dev-token loopback gate (SEC-02) —
found broken for real in CI (BRIEF v1.5): a host process hitting the
Docker-published port at 127.0.0.1 never reaches uvicorn as 127.0.0.1,
because Docker's NAT rewrites the source address to the bridge gateway IP.
Native/non-container dev never exercised this path, so it shipped with a
check that only worked when the API ran outside a container."""

from types import SimpleNamespace
from unittest.mock import mock_open, patch

import pytest
from fastapi import HTTPException

from app.routers import auth as auth_router
from app.routers.auth import _container_default_gateway, _is_loopback, issue_dev_token

# A minimal, real-shaped /proc/net/route: header line + one default-route
# (destination 00000000) entry with gateway 0101A8C0 little-endian hex,
# which decodes to 192.168.1.1 — the same format the real file uses.
_FAKE_ROUTE_TABLE = (
    "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
    "eth0\t00000000\t0101A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
)


def _request(host: str | None):
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(client=client)


def test_real_loopback_addresses_pass():
    assert _is_loopback(_request("127.0.0.1"))
    assert _is_loopback(_request("::1"))
    assert _is_loopback(_request("localhost"))


def test_no_client_info_fails_closed():
    assert not _is_loopback(_request(None))


def test_arbitrary_remote_address_is_rejected():
    assert not _is_loopback(_request("203.0.113.7"))


def test_docker_bridge_gateway_is_treated_as_loopback():
    # This is the exact case that broke in CI: the host's 127.0.0.1 request
    # arrives at the container looking like it came from the bridge gateway.
    with patch("builtins.open", mock_open(read_data=_FAKE_ROUTE_TABLE)):
        assert _container_default_gateway() == "192.168.1.1"
        assert _is_loopback(_request("192.168.1.1"))


def test_sibling_container_on_the_same_network_is_still_rejected():
    # A sibling container calling api:8000 directly presents its OWN
    # container IP, not the gateway's — this must stay blocked, or the
    # fix would widen SEC-02's gate to the whole compose network.
    with patch("builtins.open", mock_open(read_data=_FAKE_ROUTE_TABLE)):
        assert not _is_loopback(_request("192.168.1.42"))


def test_missing_proc_net_route_fails_closed():
    # e.g. running natively on macOS/Windows outside any container/Linux
    # netns — no default gateway to compare against, so only real loopback
    # addresses are accepted.
    with patch("builtins.open", side_effect=FileNotFoundError):
        assert _container_default_gateway() is None
        assert not _is_loopback(_request("192.168.1.1"))


def test_dev_token_still_issued_from_loopback_in_production():
    # Found for real in CI (BRIEF v1.6): this endpoint used to 404
    # unconditionally in production, silently breaking the packaged
    # desktop app's own auth bootstrap (VANTAGE_ENV=production is what
    # infra/.env.prod.template sets, and apps/web's fetchDevToken has no
    # fallback) — nobody had run the packaged app end-to-end before that
    # brief's acceptance test. Loopback-only is the real gate now, in
    # every environment.
    original_env = auth_router.settings.vantage_env
    auth_router.settings.vantage_env = "production"
    try:
        response = issue_dev_token(_request("127.0.0.1"))
        assert response.access_token
    finally:
        auth_router.settings.vantage_env = original_env


def test_dev_token_still_rejects_non_loopback_in_production():
    original_env = auth_router.settings.vantage_env
    auth_router.settings.vantage_env = "production"
    try:
        with pytest.raises(HTTPException) as exc_info:
            issue_dev_token(_request("203.0.113.7"))
        assert exc_info.value.status_code == 403
    finally:
        auth_router.settings.vantage_env = original_env


# BRIEF v1.8: found for real on a Podman install — _is_loopback's network
# heuristic doesn't generalize to every container runtime (confirmed:
# fails under Podman's rootless networking, which presents a host-
# originated published-port connection as neither a literal loopback
# address nor the container's own default gateway). A per-install shared
# secret (same pattern as TILER_TOKEN/INFERENCE_TOKEN) is an ADDITIONAL
# accepted path — every test below confirms it's additive, never a
# replacement: the loopback tests above must keep passing unchanged, and
# the secret path must never fail open.
class TestDevTokenSecret:
    def setup_method(self):
        self._original_secret = auth_router.settings.dev_token_secret
        auth_router.settings.dev_token_secret = "a-real-generated-secret-not-the-default-1234"

    def teardown_method(self):
        auth_router.settings.dev_token_secret = self._original_secret

    def test_correct_secret_is_accepted_even_from_a_non_loopback_address(self):
        # This is the actual Podman fix: a request from an address that
        # fails every network-based check must still succeed if it
        # presents the real, generated secret.
        response = issue_dev_token(
            _request("10.89.0.14"), x_dev_token_secret="a-real-generated-secret-not-the-default-1234"
        )
        assert response.access_token

    def test_wrong_secret_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            issue_dev_token(_request("10.89.0.14"), x_dev_token_secret="some-guessed-value")
        assert exc_info.value.status_code == 403

    def test_missing_secret_header_falls_back_to_loopback_check_only(self):
        # No header presented at all (e.g. an install predating this fix,
        # or a caller that simply doesn't know it) — must behave exactly
        # like before: loopback passes, non-loopback is rejected.
        assert issue_dev_token(_request("127.0.0.1"), x_dev_token_secret=None).access_token
        with pytest.raises(HTTPException):
            issue_dev_token(_request("10.89.0.14"), x_dev_token_secret=None)

    def test_known_default_placeholder_secret_is_never_accepted(self):
        # Guards against exactly the failure mode caught during review: an
        # install whose .env predates this fix has no real generated
        # secret, so settings.dev_token_secret falls back to this same
        # known, publicly-documented placeholder string. It must never be
        # treated as a valid secret even if somehow presented as a header —
        # otherwise anyone who's read this file could bypass the gate.
        auth_router.settings.dev_token_secret = "change-me-dev-token-secret"
        with pytest.raises(HTTPException):
            issue_dev_token(_request("10.89.0.14"), x_dev_token_secret="change-me-dev-token-secret")
