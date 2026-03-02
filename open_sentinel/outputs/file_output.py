"""File alert output: appends alerts as JSON Lines to a file."""

from __future__ import annotations

import asyncio
from pathlib import Path

from open_sentinel.interfaces import AlertOutput
from open_sentinel.types import Alert

_SEVERITY_ORDER = {"low": 1, "moderate": 2, "high": 3, "critical": 4}


class FileOutput(AlertOutput):
    def __init__(self, path: str, min_severity: str = "low"):
        self._path = Path(path)
        self._min_severity = min_severity

    def name(self) -> str:
        return "file"

    def _write_line(self, line: str) -> None:
        with open(self._path, "a") as f:
            f.write(line)

    async def emit(self, alert: Alert) -> bool:
        line = alert.model_dump_json() + "\n"
        await asyncio.to_thread(self._write_line, line)
        return True

    def accepts(self, alert: Alert) -> bool:
        alert_level = _SEVERITY_ORDER.get(alert.severity, 0)
        min_level = _SEVERITY_ORDER.get(self._min_severity, 1)
        return alert_level >= min_level
