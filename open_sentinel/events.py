"""EventBus for lifecycle event emission and subscription."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self, history_size: int = 1000):
        self._handlers: Dict[str, List[Callable]] = {}
        self._pattern_handlers: List[tuple[str, Callable]] = []
        self._history: deque[Dict[str, Any]] = deque(maxlen=history_size)

    def subscribe(self, event_name: str, handler: Callable) -> None:
        self._handlers.setdefault(event_name, []).append(handler)

    def subscribe_pattern(self, prefix: str, handler: Callable) -> None:
        self._pattern_handlers.append((prefix, handler))

    def emit(self, event_name: str, **payload: Any) -> None:
        event = {"event": event_name, **payload}
        self._history.append(event)

        for handler in self._handlers.get(event_name, []):
            try:
                handler(event)
            except Exception:
                logger.exception("Handler error for event %s", event_name)

        for prefix, handler in self._pattern_handlers:
            if event_name.startswith(prefix):
                try:
                    handler(event)
                except Exception:
                    logger.exception("Pattern handler error for event %s", event_name)

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()
