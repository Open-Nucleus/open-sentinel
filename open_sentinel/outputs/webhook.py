"""Webhook alert output: POSTs alerts to an HTTP endpoint."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Dict, Optional

import httpx

from open_sentinel.interfaces import AlertOutput
from open_sentinel.types import Alert

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"low": 1, "moderate": 2, "high": 3, "critical": 4}


class WebhookOutput(AlertOutput):
    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        min_severity: str = "high",
        timeout_seconds: int = 30,
        secret: Optional[str] = None,
    ):
        self._url = url
        self._headers = headers or {}
        self._min_severity = min_severity
        self._timeout = timeout_seconds
        self._secret = secret
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    def name(self) -> str:
        return "webhook"

    def accepts(self, alert: Alert) -> bool:
        alert_level = _SEVERITY_ORDER.get(alert.severity, 0)
        min_level = _SEVERITY_ORDER.get(self._min_severity, 1)
        return alert_level >= min_level

    async def emit(self, alert: Alert) -> bool:
        body = alert.model_dump_json()
        headers = {**self._headers, "Content-Type": "application/json"}

        if self._secret:
            sig = hmac.new(
                self._secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Sentinel-Signature"] = f"sha256={sig}"

        try:
            resp = await self._client.post(self._url, content=body, headers=headers)
            return resp.status_code < 400
        except (httpx.HTTPError, Exception):
            logger.exception("Webhook delivery failed to %s", self._url)
            return False
