"""Tests for EmailOutput."""

from unittest.mock import AsyncMock, patch

from open_sentinel.outputs.email_output import EmailOutput
from open_sentinel.testing.fixtures import make_alert


class TestEmailOutputEmit:
    @patch("aiosmtplib.send", new_callable=AsyncMock)
    async def test_emit_success(self, mock_send):
        output = EmailOutput(
            smtp_host="smtp.example.com",
            smtp_port=587,
            from_addr="sentinel@example.com",
            to_addrs=["doctor@example.com"],
        )
        result = await output.emit(make_alert(severity="critical", title="Test Email"))
        assert result is True
        mock_send.assert_called_once()

    @patch("aiosmtplib.send", new_callable=AsyncMock)
    async def test_emit_passes_smtp_config(self, mock_send):
        output = EmailOutput(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user",
            password="pass",
            from_addr="sentinel@example.com",
            to_addrs=["doctor@example.com"],
            use_tls=True,
        )
        await output.emit(make_alert(severity="critical"))
        call_kwargs = mock_send.call_args
        assert call_kwargs.kwargs["hostname"] == "smtp.example.com"
        assert call_kwargs.kwargs["port"] == 587
        assert call_kwargs.kwargs["start_tls"] is True

    @patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("SMTP error"))
    async def test_emit_failure_returns_false(self, mock_send):
        output = EmailOutput(
            smtp_host="smtp.example.com",
            from_addr="sentinel@example.com",
            to_addrs=["doctor@example.com"],
        )
        result = await output.emit(make_alert(severity="critical"))
        assert result is False


class TestEmailOutputAccepts:
    def test_default_min_severity_is_high(self):
        output = EmailOutput()
        assert output.accepts(make_alert(severity="low")) is False
        assert output.accepts(make_alert(severity="moderate")) is False
        assert output.accepts(make_alert(severity="high")) is True
        assert output.accepts(make_alert(severity="critical")) is True

    def test_custom_min_severity(self):
        output = EmailOutput(min_severity="moderate")
        assert output.accepts(make_alert(severity="low")) is False
        assert output.accepts(make_alert(severity="moderate")) is True
        assert output.accepts(make_alert(severity="high")) is True


class TestEmailOutputBody:
    def test_body_contains_required_fields(self):
        output = EmailOutput()
        alert = make_alert(
            severity="critical",
            title="Test Alert",
            skill_name="test-skill",
            site_id="clinic-01",
        )
        body = output._build_body(alert)
        assert "CRITICAL" in body
        assert "Test Alert" in body
        assert "test-skill" in body
        assert "clinic-01" in body
        assert "REQUIRES CLINICAL REVIEW" in body

    def test_body_includes_ai_provenance(self):
        output = EmailOutput()
        alert = make_alert(
            severity="high",
            ai_generated=True,
            ai_confidence=0.85,
        )
        body = output._build_body(alert)
        assert "AI Generated: True" in body
        assert "0.85" in body

    def test_body_includes_patient_id(self):
        output = EmailOutput()
        alert = make_alert(severity="high", patient_id="patient-42")
        body = output._build_body(alert)
        assert "patient-42" in body


class TestEmailOutputMeta:
    def test_name(self):
        output = EmailOutput()
        assert output.name() == "email"
