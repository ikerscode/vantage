"""Real regression coverage for the dev-token loopback gate (SEC-02) —
found broken for real in CI (BRIEF v1.5): a host process hitting the
Docker-published port at 127.0.0.1 never reaches uvicorn as 127.0.0.1,
because Docker's NAT rewrites the source address to the bridge gateway IP.
Native/non-container dev never exercised this path, so it shipped with a
check that only worked when the API ran outside a container."""

from types import SimpleNamespace
from unittest.mock import mock_open, patch

from app.routers.auth import _container_default_gateway, _is_loopback

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
