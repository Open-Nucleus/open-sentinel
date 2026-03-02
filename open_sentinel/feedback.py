"""Feedback processor: human-in-the-loop calibration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from open_sentinel.events import EventBus
from open_sentinel.interfaces import MemoryStore

logger = logging.getLogger(__name__)

THRESHOLD_CEILING = 0.95
THRESHOLD_INCREMENT = 0.05
DEFAULT_THRESHOLD = 0.6


class FeedbackProcessor:
    def __init__(self, memory: MemoryStore, events: EventBus):
        self._memory = memory
        self._events = events

    async def process_feedback(
        self,
        alert_id: str,
        outcome: str,
        feedback: str | None = None,
    ) -> None:
        # Update alert outcome
        await self._memory.update_alert_outcome(alert_id, outcome, feedback)

        # Update episode outcome
        await self._memory.update_episode_outcome(alert_id, outcome, feedback)

        # Get the alert to find skill_name
        alert = await self._memory.get_alert(alert_id)
        if alert is None:
            logger.warning("Alert %s not found for feedback processing", alert_id)
            return

        skill_name = alert.skill_name

        if outcome == "dismissed":
            # False positive: raise confidence threshold
            current = await self._memory.get_skill_state(skill_name, "confidence_threshold")
            if current is None:
                current = DEFAULT_THRESHOLD
            old_threshold = current
            new_threshold = min(THRESHOLD_CEILING, current + THRESHOLD_INCREMENT)
            await self._memory.set_skill_state(
                skill_name, "confidence_threshold", new_threshold
            )
            self._events.emit(
                "skill.calibrated",
                skill=skill_name,
                reason="false_positive",
                old_threshold=old_threshold,
                new_threshold=new_threshold,
            )
            logger.info(
                "Skill %s threshold raised: %.2f -> %.2f (false positive)",
                skill_name,
                old_threshold,
                new_threshold,
            )

        elif outcome == "confirmed":
            await self._memory.set_skill_state(
                skill_name,
                "last_confirmed",
                datetime.now(timezone.utc).isoformat(),
            )

        self._events.emit(
            "alert.reviewed",
            alert_id=alert_id,
            outcome=outcome,
            feedback=feedback,
        )
