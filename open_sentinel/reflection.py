"""Reflection engine: critique-then-refine loop."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from open_sentinel.events import EventBus
from open_sentinel.interfaces import LLMEngine, Skill
from open_sentinel.resources import ResourceManager
from open_sentinel.types import AnalysisContext

logger = logging.getLogger(__name__)


def _parse_structured(response_text: str) -> List[Dict[str, Any]]:
    """Parse LLM response text into a list of finding dicts."""
    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            return data.get("findings", [data])
        if isinstance(data, list):
            return data
        return [{"text": str(data)}]
    except json.JSONDecodeError:
        return [{"text": response_text}]


class ReflectionEngine:
    def __init__(
        self,
        resource_manager: ResourceManager,
        events: EventBus,
    ):
        self._resource_manager = resource_manager
        self._events = events

    async def run_reflection_loop(
        self,
        findings: List[Dict[str, Any]],
        skill: Skill,
        ctx: AnalysisContext,
        llm: LLMEngine,
        clinical_context: str,
        schema: Optional[Dict[str, Any]] = None,
        run_id: str = "",
    ) -> tuple[List[Dict[str, Any]], int]:
        """Run critique→reflect loop. Returns (refined_findings, reflection_count)."""
        max_ref = min(skill.max_reflections(), self._resource_manager.max_reflections())
        reflection_count = 0

        for i in range(max_ref):
            critique = skill.critique_findings(findings, ctx)
            if critique == "ACCEPT":
                break

            self._events.emit(
                "skill.reflecting",
                run_id=run_id,
                iteration=i + 1,
                critique_summary=critique[:200],
            )

            response = await llm.reflect(
                original_findings=findings,
                critique=critique,
                clinical_context=clinical_context,
                schema=schema,
            )

            findings = _parse_structured(response.text)
            reflection_count += 1

        return findings, reflection_count
