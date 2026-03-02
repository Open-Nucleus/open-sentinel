"""Tests for WebhookOutput."""

import hashlib
import hmac
import json

import httpx

from open_sentinel.outputs.webhook import WebhookOutput
from open_sentinel.testing.fixtures import make_alert


class MockTransport(httpx.AsyncBaseTransport):
    """Mock httpx transport for testing."""

    def __init__(self, status_code: int = 200, raise_error: bool = False):
        self._status_code = status_code
        self._raise_error = raise_error
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        if self._raise_error:
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(status_code=self._status_code)


class TestWebhookOutputEmit:
    async def test_emit_success(self):
        transport = MockTransport(status_code=200)
        output = WebhookOutput(url="https://example.com/hook")
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical"))
        assert result is True
        assert transport.last_request is not None
        assert transport.last_request.url == "https://example.com/hook"

    async def test_emit_sends_json(self):
        transport = MockTransport(status_code=200)
        output = WebhookOutput(url="https://example.com/hook")
        output._client = httpx.AsyncClient(transport=transport)

        alert = make_alert(severity="critical", title="Test Webhook")
        await output.emit(alert)

        body = json.loads(transport.last_request.content)
        assert body["title"] == "Test Webhook"
        assert body["severity"] == "critical"

    async def test_emit_failure_returns_false(self):
        transport = MockTransport(status_code=500)
        output = WebhookOutput(url="https://example.com/hook")
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical"))
        assert result is False

    async def test_emit_connection_error_returns_false(self):
        transport = MockTransport(raise_error=True)
        output = WebhookOutput(url="https://example.com/hook")
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical"))
        assert result is False

    async def test_emit_custom_headers(self):
        transport = MockTransport(status_code=200)
        output = WebhookOutput(
            url="https://example.com/hook",
            headers={"Authorization": "Bearer token123"},
        )
        output._client = httpx.AsyncClient(transport=transport)

        await output.emit(make_alert(severity="critical"))
        assert transport.last_request.headers["authorization"] == "Bearer token123"
        assert transport.last_request.headers["content-type"] == "application/json"


class TestWebhookOutputSignature:
    async def test_hmac_signature(self):
        transport = MockTransport(status_code=200)
        secret = "my-secret-key"
        output = WebhookOutput(url="https://example.com/hook", secret=secret)
        output._client = httpx.AsyncClient(transport=transport)

        alert = make_alert(severity="critical")
        await output.emit(alert)

        body = transport.last_request.content
        expected_sig = hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

        sig_header = transport.last_request.headers["x-sentinel-signature"]
        assert sig_header == f"sha256={expected_sig}"

    async def test_no_signature_without_secret(self):
        transport = MockTransport(status_code=200)
        output = WebhookOutput(url="https://example.com/hook")
        output._client = httpx.AsyncClient(transport=transport)

        await output.emit(make_alert(severity="critical"))
        assert "x-sentinel-signature" not in transport.last_request.headers


class TestWebhookOutputAccepts:
    def test_default_min_severity_is_high(self):
        output = WebhookOutput(url="https://example.com/hook")
        assert output.accepts(make_alert(severity="low")) is False
        assert output.accepts(make_alert(severity="moderate")) is False
        assert output.accepts(make_alert(severity="high")) is True
        assert output.accepts(make_alert(severity="critical")) is True

    def test_custom_min_severity(self):
        output = WebhookOutput(url="https://example.com/hook", min_severity="low")
        assert output.accepts(make_alert(severity="low")) is True
        assert output.accepts(make_alert(severity="critical")) is True


class TestWebhookOutputMeta:
    def test_name(self):
        output = WebhookOutput(url="https://example.com/hook")
        assert output.name() == "webhook"
