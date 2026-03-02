"""Guardrail pipeline: confidence gate, hallucination detection, rate limiting."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from open_sentinel.events import EventBus
from open_sentinel.interfaces import MemoryStore
from open_sentinel.types import Alert, AnalysisContext

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.6


def _evidence_exists_in_data(evidence: Dict[str, Any], data: Dict[str, Any]) -> bool:
    """Check if alert evidence references data that actually exists in fetched data."""
    if not evidence:
        return True  # No evidence to validate
    if not data:
        return False  # Evidence claimed but no data to validate against

    for key, value in evidence.items():
        found = False
        for data_key, data_values in data.items():
            if isinstance(data_values, list):
                for record in data_values:
                    if isinstance(record, dict) and key in record:
                        found = True
                        break
            elif isinstance(data_values, dict) and key in data_values:
                found = True
            if found:
                break
        if not found:
            return False
    return True


class GuardrailPipeline:
    def __init__(
        self,
        memory: MemoryStore,
        events: EventBus,
        max_critical_per_hour: int = 10,
    ):
        self._memory = memory
        self._events = events
        self._max_critical_per_hour = max_critical_per_hour

    async def apply(
        self,
        alerts: List[Alert],
        ctx: AnalysisContext,
        skill_name: str,
    ) -> List[Alert]:
        passed: List[Alert] = []

        for alert in alerts:
            # Gate 1: Confidence threshold
            if alert.ai_generated and alert.ai_confidence is not None:
                threshold = await self._memory.get_skill_state(
                    skill_name, "confidence_threshold"
                )
                if threshold is None:
                    threshold = DEFAULT_CONFIDENCE_THRESHOLD
                if alert.ai_confidence < threshold:
                    self._events.emit(
                        "alert.gated",
                        reason="below_confidence",
                        alert_title=alert.title,
                        confidence=alert.ai_confidence,
                        threshold=threshold,
                    )
                    logger.info(
                        "Alert gated (confidence %.2f < %.2f): %s",
                        alert.ai_confidence,
                        threshold,
                        alert.title,
                    )
                    continue

            # Gate 2: Hallucination detection
            if alert.ai_generated and alert.evidence:
                if not _evidence_exists_in_data(alert.evidence, ctx.data):
                    self._events.emit(
                        "alert.gated",
                        reason="hallucinated_evidence",
                        alert_title=alert.title,
                    )
                    logger.warning("Alert gated (hallucinated evidence): %s", alert.title)
                    continue

            # Gate 3: Rate limiting
            if alert.severity == "critical":
                count = await self._memory.count_recent_alerts(
                    skill_name, severity="critical", window_hours=1
                )
                if count >= self._max_critical_per_hour:
                    self._events.emit(
                        "alert.gated",
                        reason="rate_limited",
                        alert_title=alert.title,
                    )
                    logger.warning("Alert gated (rate limited): %s", alert.title)
                    continue

            # Enforce requires_review invariant
            alert = alert.model_copy(update={"requires_review": True})
            passed.append(alert)

        return passed
