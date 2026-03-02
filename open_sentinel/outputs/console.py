"""Console alert output: prints alerts to stdout."""

from __future__ import annotations

import sys

from open_sentinel.interfaces import AlertOutput
from open_sentinel.types import Alert


class ConsoleOutput(AlertOutput):
    def __init__(self, json_format: bool = False):
        self._json_format = json_format

    def name(self) -> str:
        return "console"

    async def emit(self, alert: Alert) -> bool:
        if self._json_format:
            print(alert.model_dump_json(indent=2), file=sys.stdout)
        else:
            print(
                f"[{alert.severity.upper()}] {alert.title}\n"
                f"  Skill: {alert.skill_name}\n"
                f"  Site: {alert.site_id or 'N/A'}\n"
                f"  AI: {alert.ai_generated} | Confidence: {alert.ai_confidence}\n"
                f"  Review required: {alert.requires_review}\n"
                f"  {alert.description}",
                file=sys.stdout,
            )
        return True

    def accepts(self, alert: Alert) -> bool:
        return True
