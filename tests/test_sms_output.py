"""Tests for SmsOutput."""

import httpx

from open_sentinel.outputs.sms import SmsOutput
from open_sentinel.testing.fixtures import make_alert


class MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, status_code: int = 200, raise_error: bool = False):
        self._status_code = status_code
        self._raise_error = raise_error
        self.last_request: httpx.Request | None = None
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        self.requests.append(request)
        if self._raise_error:
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(status_code=self._status_code)


class TestSmsOutputAfricasTalking:
    async def test_emit_success(self):
        transport = MockTransport(status_code=200)
        output = SmsOutput(
            provider="africastalking",
            api_key="test-key",
            recipients=["+254700000001"],
            sender_id="Sentinel",
        )
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical", title="Test SMS"))
        assert result is True
        assert transport.last_request is not None
        assert "africastalking" in str(transport.last_request.url)

    async def test_emit_sends_form_data(self):
        transport = MockTransport(status_code=200)
        output = SmsOutput(
            provider="africastalking",
            api_key="test-key",
            recipients=["+254700000001"],
            sender_id="Sentinel",
        )
        output._client = httpx.AsyncClient(transport=transport)

        await output.emit(make_alert(severity="critical", title="Cholera outbreak"))
        body = transport.last_request.content.decode()
        # Phone number is URL-encoded in form data
        assert "254700000001" in body
        assert "apikey" in str(transport.last_request.headers)

    async def test_emit_failure_returns_false(self):
        transport = MockTransport(status_code=500)
        output = SmsOutput(
            provider="africastalking",
            api_key="test-key",
            recipients=["+254700000001"],
        )
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical"))
        assert result is False


class TestSmsOutputTwilio:
    async def test_emit_success(self):
        transport = MockTransport(status_code=201)
        output = SmsOutput(
            provider="twilio",
            api_key="auth-token",
            account_sid="AC123",
            from_number="+15551234567",
            recipients=["+254700000001"],
        )
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical", title="Test Twilio"))
        assert result is True
        assert transport.last_request is not None
        assert "AC123" in str(transport.last_request.url)

    async def test_emit_multiple_recipients(self):
        transport = MockTransport(status_code=201)
        output = SmsOutput(
            provider="twilio",
            api_key="auth-token",
            account_sid="AC123",
            from_number="+15551234567",
            recipients=["+254700000001", "+254700000002"],
        )
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical"))
        assert result is True
        assert len(transport.requests) == 2

    async def test_emit_failure_returns_false(self):
        transport = MockTransport(status_code=400)
        output = SmsOutput(
            provider="twilio",
            api_key="auth-token",
            account_sid="AC123",
            from_number="+15551234567",
            recipients=["+254700000001"],
        )
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical"))
        assert result is False


class TestSmsOutputAccepts:
    def test_default_min_severity_is_critical(self):
        output = SmsOutput()
        assert output.accepts(make_alert(severity="low")) is False
        assert output.accepts(make_alert(severity="moderate")) is False
        assert output.accepts(make_alert(severity="high")) is False
        assert output.accepts(make_alert(severity="critical")) is True

    def test_custom_min_severity(self):
        output = SmsOutput(min_severity="high")
        assert output.accepts(make_alert(severity="moderate")) is False
        assert output.accepts(make_alert(severity="high")) is True
        assert output.accepts(make_alert(severity="critical")) is True


class TestSmsOutputBody:
    def test_body_truncated_to_160(self):
        output = SmsOutput()
        alert = make_alert(
            severity="critical",
            title="A" * 200,
            site_id="site-1",
        )
        body = output._format_body(alert)
        assert len(body) <= 160

    def test_body_includes_severity_and_site(self):
        output = SmsOutput()
        alert = make_alert(severity="critical", title="Test", site_id="clinic-01")
        body = output._format_body(alert)
        assert "[CRITICAL]" in body
        assert "clinic-01" in body
        assert "Review required" in body


class TestSmsOutputError:
    async def test_connection_error_returns_false(self):
        transport = MockTransport(raise_error=True)
        output = SmsOutput(
            provider="africastalking",
            api_key="test-key",
            recipients=["+254700000001"],
        )
        output._client = httpx.AsyncClient(transport=transport)

        result = await output.emit(make_alert(severity="critical"))
        assert result is False

    async def test_unknown_provider_returns_false(self):
        output = SmsOutput(provider="unknown")
        result = await output.emit(make_alert(severity="critical"))
        assert result is False


class TestSmsOutputMeta:
    def test_name(self):
        output = SmsOutput()
        assert output.name() == "sms"
