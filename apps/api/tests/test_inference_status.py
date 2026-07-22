"""The /api/inference/status proxy must translate every failure mode of the
inference service's /health into an honest {reachable: false} rather than a
500 or a hang — the UI note it drives is only trustworthy if "down",
"slow", and "returning garbage" all read as unreachable."""

import httpx
import pytest

from app.routers import inference as inference_router
from app.schemas.auth import UserClaims


def _user() -> UserClaims:
    return UserClaims(sub="test-user", name="Test User", roles=["analyst"])


class _FakeResponse:
    def __init__(self, payload, status_error: bool = False):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise httpx.HTTPStatusError("boom", request=None, response=None)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_reports_backend_and_device_when_inference_is_up(monkeypatch):
    monkeypatch.setattr(
        inference_router.httpx,
        "get",
        lambda url, timeout: _FakeResponse(
            {"status": "ok", "model_backend": "torchvision_fasterrcnn_vessel", "device": "cpu"}
        ),
    )
    status = inference_router.inference_status(_user())
    assert status.reachable is True
    assert status.model_backend == "torchvision_fasterrcnn_vessel"
    assert status.device == "cpu"


def test_connection_failure_reads_as_unreachable_not_a_500(monkeypatch):
    def _raise(url, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(inference_router.httpx, "get", _raise)
    status = inference_router.inference_status(_user())
    assert status.reachable is False
    assert status.model_backend is None


def test_http_error_status_reads_as_unreachable(monkeypatch):
    monkeypatch.setattr(
        inference_router.httpx, "get", lambda url, timeout: _FakeResponse({}, status_error=True)
    )
    assert inference_router.inference_status(_user()).reachable is False


def test_non_json_body_reads_as_unreachable(monkeypatch):
    monkeypatch.setattr(
        inference_router.httpx,
        "get",
        lambda url, timeout: _FakeResponse(ValueError("not json")),
    )
    assert inference_router.inference_status(_user()).reachable is False


def test_older_inference_health_without_backend_field_is_still_reachable(monkeypatch):
    # A not-yet-rebuilt inference container serves the pre-field {"status":"ok"}
    # shape — that's a reachable service whose backend is unknown, not an error.
    monkeypatch.setattr(
        inference_router.httpx, "get", lambda url, timeout: _FakeResponse({"status": "ok"})
    )
    status = inference_router.inference_status(_user())
    assert status.reachable is True
    assert status.model_backend is None


@pytest.mark.parametrize("field", ["model_backend", "device"])
def test_status_schema_defaults_are_none(field):
    from app.schemas.inference import InferenceStatus

    assert getattr(InferenceStatus(reachable=False), field) is None
