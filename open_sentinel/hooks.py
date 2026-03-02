"""HookRegistry for before/after extension points."""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Dict, List

logger = logging.getLogger(__name__)

VALID_HOOKS = frozenset({
    "before_data_fetch",
    "after_data_fetch",
    "before_skill_run",
    "after_skill_run",
    "before_alert_emit",
    "after_alert_emit",
    "before_llm_prompt",
    "after_llm_response",
    "on_reflection",
    "on_degraded_mode",
    "on_feedback",
})


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: Dict[str, List[Callable[..., Coroutine]]] = {}

    def register(self, hook_name: str, handler: Callable[..., Coroutine]) -> None:
        if hook_name not in VALID_HOOKS:
            raise ValueError(
                f"Invalid hook name: {hook_name}. Valid hooks: {sorted(VALID_HOOKS)}"
            )
        self._hooks.setdefault(hook_name, []).append(handler)

    async def run(self, hook_name: str, *args: Any, **kwargs: Any) -> None:
        for handler in self._hooks.get(hook_name, []):
            try:
                await handler(*args, **kwargs)
            except Exception:
                logger.exception("Hook error in %s", hook_name)
