"""SkillTestHarness: simplified agent environment for testing skills."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from open_sentinel.events import EventBus
from open_sentinel.guardrails import GuardrailPipeline
from open_sentinel.hooks import HookRegistry
from open_sentinel.interfaces import LLMEngine, Skill
from open_sentinel.llm.mock import MockLLMEngine
from open_sentinel.memory import SqliteMemoryStore
from open_sentinel.reflection import ReflectionEngine, _parse_structured
from open_sentinel.resources import ResourceManager
from open_sentinel.types import (
    AgentConfig,
    Alert,
    AnalysisContext,
    DataEvent,
)


@dataclass
class SkillTestResult:
    alerts: List[Alert] = field(default_factory=list)
    reflection_count: int = 0
    degraded: bool = False
    findings: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)


class SkillTestHarness:
    def __init__(
        self,
        skill: Skill,
        llm: Optional[LLMEngine] = None,
        config: Optional[AgentConfig] = None,
    ):
        self.skill = skill
        self.llm = llm or MockLLMEngine()
        self.config = config or AgentConfig(state_db_path=":memory:")
        self.memory = SqliteMemoryStore(":memory:")
        self.events = EventBus()
        self.hooks = HookRegistry()
        self.resource_manager = ResourceManager(self.config.hardware)
        self._data: Dict[str, Any] = {}
        self._site_id: Optional[str] = None
        self._trigger_event: Optional[DataEvent] = None

    def set_data(self, data: Dict[str, Any]) -> "SkillTestHarness":
        self._data = data
        return self

    def set_site_id(self, site_id: str) -> "SkillTestHarness":
        self._site_id = site_id
        return self

    def set_trigger_event(self, event: DataEvent) -> "SkillTestHarness":
        self._trigger_event = event
        return self

    def run(self, **kwargs) -> SkillTestResult:
        return asyncio.get_event_loop().run_until_complete(self.run_async(**kwargs))

    async def run_async(self, degraded: bool = False) -> SkillTestResult:
        await self.memory.initialize()

        try:
            ctx = AnalysisContext(
                trigger="event",
                trigger_event=self._trigger_event,
                data=self._data,
                site_id=self._site_id,
                config=self.config.skill_config.get(self.skill.name(), {}),
                llm=self.llm,
                memory=self.memory,
                episodes=[],
                baselines={},
                previous_alerts=[],
            )

            if degraded or not await self.llm.available():
                # Degraded mode: rules only
                alerts = self.skill.rule_fallback(ctx)
                for i, alert in enumerate(alerts):
                    alerts[i] = alert.model_copy(update={
                        "ai_generated": False,
                        "ai_reasoning": "[LLM unavailable — rule-based detection only]",
                        "rule_validated": True,
                    })
                return SkillTestResult(
                    alerts=alerts,
                    reflection_count=0,
                    degraded=True,
                    events=self.events.history,
                )

            # LLM path
            prompt = self.skill.build_prompt(ctx)
            schema = self.skill.response_schema()

            response = await self.llm.reason(
                "You are a clinical surveillance analyst.",
                prompt,
                self.skill.goal() or "Analyze",
                schema,
            )
            findings = _parse_structured(response.text)

            # Reflection
            reflection_engine = ReflectionEngine(self.resource_manager, self.events)
            findings, reflection_count = await reflection_engine.run_reflection_loop(
                findings, self.skill, ctx, self.llm, prompt, schema
            )

            # Convert to alerts
            alerts: List[Alert] = []
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                alert = Alert(
                    skill_name=self.skill.name(),
                    severity=finding.get("severity", "moderate"),
                    category=finding.get("category", ""),
                    title=finding.get("title", "Untitled"),
                    description=finding.get("description", ""),
                    site_id=self._site_id,
                    evidence=finding.get("evidence"),
                    measured_value=finding.get("measured_value"),
                    threshold_value=finding.get("threshold_value"),
                    ai_generated=True,
                    ai_confidence=finding.get("confidence") or response.confidence,
                    ai_model=response.model,
                    ai_reasoning=finding.get("reasoning", ""),
                    reflection_iterations=reflection_count,
                    dedup_key=finding.get("dedup_key"),
                )
                alerts.append(alert)

            # Guardrails
            guardrails = GuardrailPipeline(
                self.memory, self.events, self.config.max_critical_per_hour
            )
            alerts = await guardrails.apply(alerts, ctx, self.skill.name())

            return SkillTestResult(
                alerts=alerts,
                reflection_count=reflection_count,
                degraded=False,
                findings=findings,
                events=self.events.history,
            )
        finally:
            await self.memory.close()
