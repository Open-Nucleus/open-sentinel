"""Email alert output: sends alerts via SMTP."""

from __future__ import annotations

import logging
from email.mime.text import MIMEText
from typing import List

import aiosmtplib

from open_sentinel.interfaces import AlertOutput
from open_sentinel.types import Alert

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"low": 1, "moderate": 2, "high": 3, "critical": 4}


class EmailOutput(AlertOutput):
    def __init__(
        self,
        smtp_host: str = "localhost",
        smtp_port: int = 587,
        username: str = "",
        password: str = "",
        from_addr: str = "",
        to_addrs: List[str] | None = None,
        min_severity: str = "high",
        use_tls: bool = True,
    ):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._from_addr = from_addr
        self._to_addrs = to_addrs or []
        self._min_severity = min_severity
        self._use_tls = use_tls

    def name(self) -> str:
        return "email"

    def accepts(self, alert: Alert) -> bool:
        alert_level = _SEVERITY_ORDER.get(alert.severity, 0)
        min_level = _SEVERITY_ORDER.get(self._min_severity, 1)
        return alert_level >= min_level

    def _build_body(self, alert: Alert) -> str:
        lines = [
            f"Severity: {alert.severity.upper()}",
            f"Title: {alert.title}",
            f"Skill: {alert.skill_name}",
        ]
        if alert.site_id:
            lines.append(f"Site: {alert.site_id}")
        if alert.patient_id:
            lines.append(f"Patient: {alert.patient_id}")
        if alert.description:
            lines.append(f"\nDescription:\n{alert.description}")
        lines.append(f"\nAI Generated: {alert.ai_generated}")
        if alert.ai_model:
            lines.append(f"AI Model: {alert.ai_model}")
        if alert.ai_confidence is not None:
            lines.append(f"AI Confidence: {alert.ai_confidence}")
        lines.append(f"Reflection Iterations: {alert.reflection_iterations}")
        lines.append(f"Rule Validated: {alert.rule_validated}")
        lines.append("\n*** REQUIRES CLINICAL REVIEW ***")
        return "\n".join(lines)

    async def emit(self, alert: Alert) -> bool:
        body = self._build_body(alert)
        msg = MIMEText(body)
        msg["Subject"] = f"[Sentinel {alert.severity.upper()}] {alert.title}"
        msg["From"] = self._from_addr
        msg["To"] = ", ".join(self._to_addrs)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._smtp_host,
                port=self._smtp_port,
                username=self._username or None,
                password=self._password or None,
                start_tls=self._use_tls,
            )
            return True
        except Exception:
            logger.exception("Email delivery failed to %s", self._to_addrs)
            return False
