"""SMS alert output: sends alerts via Africa's Talking or Twilio."""

from __future__ import annotations

import logging
from typing import List, Optional

import httpx

from open_sentinel.interfaces import AlertOutput
from open_sentinel.types import Alert

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"low": 1, "moderate": 2, "high": 3, "critical": 4}

_AT_URL = "https://api.africastalking.com/version1/messaging"
_TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"


class SmsOutput(AlertOutput):
    def __init__(
        self,
        provider: str = "africastalking",
        api_key: str = "",
        recipients: Optional[List[str]] = None,
        sender_id: str = "Sentinel",
        from_number: str = "",
        account_sid: str = "",
        min_severity: str = "critical",
        timeout_seconds: int = 30,
    ):
        self._provider = provider
        self._api_key = api_key
        self._recipients = recipients or []
        self._sender_id = sender_id
        self._from_number = from_number
        self._account_sid = account_sid
        self._min_severity = min_severity
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    def name(self) -> str:
        return "sms"

    def accepts(self, alert: Alert) -> bool:
        alert_level = _SEVERITY_ORDER.get(alert.severity, 0)
        min_level = _SEVERITY_ORDER.get(self._min_severity, 1)
        return alert_level >= min_level

    def _format_body(self, alert: Alert) -> str:
        parts = [f"[{alert.severity.upper()}] {alert.title}"]
        if alert.site_id:
            parts.append(f"Site: {alert.site_id}")
        parts.append("Review required.")
        body = " | ".join(parts)
        return body[:160]

    async def emit(self, alert: Alert) -> bool:
        body = self._format_body(alert)
        try:
            if self._provider == "africastalking":
                return await self._send_africastalking(body)
            elif self._provider == "twilio":
                return await self._send_twilio(body)
            else:
                logger.error("Unknown SMS provider: %s", self._provider)
                return False
        except (httpx.HTTPError, Exception):
            logger.exception("SMS delivery failed via %s", self._provider)
            return False

    async def _send_africastalking(self, body: str) -> bool:
        to = ",".join(self._recipients)
        data = {"username": self._sender_id, "to": to, "message": body}
        headers = {
            "apiKey": self._api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        resp = await self._client.post(_AT_URL, data=data, headers=headers)
        return resp.status_code < 400

    async def _send_twilio(self, body: str) -> bool:
        url = _TWILIO_URL.format(account_sid=self._account_sid)
        auth = (self._account_sid, self._api_key)
        for recipient in self._recipients:
            data = {"From": self._from_number, "To": recipient, "Body": body}
            resp = await self._client.post(url, data=data, auth=auth)
            if resp.status_code >= 400:
                return False
        return True
