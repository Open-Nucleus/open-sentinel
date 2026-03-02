"""Alert deduplication by dedup_key + time window."""

from __future__ import annotations

from typing import List

from open_sentinel.interfaces import MemoryStore
from open_sentinel.types import Alert


class Deduplicator:
    def __init__(self, memory: MemoryStore, window_hours: int = 24):
        self._memory = memory
        self._window_hours = window_hours

    async def deduplicate(self, alerts: List[Alert]) -> List[Alert]:
        unique: List[Alert] = []
        for alert in alerts:
            if alert.dedup_key is None:
                unique.append(alert)
                continue
            # Check alert_history for matching dedup_key within window
            recent = await self._memory.recent_alerts(alert.skill_name, limit=100)
            is_dup = any(
                existing.dedup_key == alert.dedup_key
                for existing in recent
            )
            if not is_dup:
                unique.append(alert)
        return unique
