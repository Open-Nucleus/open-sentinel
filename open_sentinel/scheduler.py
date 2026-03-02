"""Cron-based skill scheduling."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Coroutine, List, Optional

from croniter import croniter

logger = logging.getLogger(__name__)


class ScheduleEntry:
    def __init__(self, skill_name: str, cron_expr: str, callback: Callable[..., Coroutine]):
        self.skill_name = skill_name
        self.cron_expr = cron_expr
        self.callback = callback
        self._cron = croniter(cron_expr, datetime.now(timezone.utc))

    def next_time(self) -> datetime:
        return self._cron.get_next(datetime).replace(tzinfo=timezone.utc)


class Scheduler:
    def __init__(self) -> None:
        self._entries: List[ScheduleEntry] = []
        self._tasks: List[asyncio.Task] = []
        self._running = False

    def register(self, skill_name: str, cron_expr: str, callback: Callable[..., Coroutine]) -> None:
        self._entries.append(ScheduleEntry(skill_name, cron_expr, callback))

    def next_wake_time(self) -> Optional[datetime]:
        if not self._entries:
            return None
        return min(entry.next_time() for entry in self._entries)

    async def start(self) -> None:
        self._running = True
        for entry in self._entries:
            task = asyncio.create_task(self._run_schedule(entry))
            self._tasks.append(task)

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def _run_schedule(self, entry: ScheduleEntry) -> None:
        while self._running:
            next_time = entry.next_time()
            now = datetime.now(timezone.utc)
            delay = (next_time - now).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                await entry.callback(entry.skill_name)
            except Exception:
                logger.exception("Scheduled skill %s failed", entry.skill_name)
