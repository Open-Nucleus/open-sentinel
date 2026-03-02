"""Tests for SentinelAgent."""

from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from open_sentinel.agent import SentinelAgent
from open_sentinel.interfaces import DataAdapter, Skill
from open_sentinel.llm.mock import MockLLMEngine
from open_sentinel.outputs.console import ConsoleOutput
from open_sentinel.types import (
    AgentConfig,
    Alert,
    AnalysisContext,
    DataEvent,
    DataRequirement,
    Priority,
)


class MockDataAdapter(DataAdapter):
    def __init__(self, data: Optional[Dict[str, List]] = None):
        self._data = data or {}
        self._events: List[DataEvent] = []

    def name(self) -> str:
        return "mock"

    async def query(
        self, resource_type: str, filters: Dict[str, Any], limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        result = self._data.get(resource_type, [])
        if limit:
            return result[:limit]
        return result

    async def count(self, resource_type: str, filters: Dict[str, Any]) -> int:
        return len(self._data.get(resource_type, []))

    async def subscribe(self, event_types: List[str]) -> AsyncIterator[DataEvent]:
        for event in self._events:
            yield event

    async def aggregate(
        self,
        resource_type: str,
        group_by: List[str],
        metric: str,
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self._data.get(resource_type, [])

    def set_events(self, events: List[DataEvent]) -> None:
        self._events = events


class DummySkill(Skill):
    def name(self) -> str:
        return "dummy-skill"

    def priority(self) -> Priority:
        return Priority.MEDIUM

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "conditions": DataRequirement(resource_type="Condition"),
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        count = len(ctx.data.get("conditions", []))
        return f"Analyze {count} conditions for anomalies."

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        conditions = ctx.data.get("conditions", [])
        if len(conditions) > 5:
            return [Alert(
                skill_name=self.name(),
                severity="high",
                title="Threshold exceeded",
                description=f"Found {len(conditions)} conditions (threshold: 5)",
                measured_value=float(len(conditions)),
                threshold_value=5.0,
            )]
        return []


@pytest.fixture
def config():
    return AgentConfig(state_db_path=":memory:", hardware="hub_16gb")


class TestSentinelAgent:
    async def test_start_emits_event(self, config):
        llm = MockLLMEngine()
        adapter = MockDataAdapter()
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)

        received = []
        agent.events.subscribe("agent.started", lambda e: received.append(e))
        await agent.start()
        await agent.stop()

        assert len(received) == 1
        assert "dummy-skill" in received[0]["skills_loaded"]

    async def test_run_skill_llm_path(self, config):
        llm = MockLLMEngine(responses=[
            {
                "findings": [{
                    "severity": "high",
                    "title": "Cholera cluster detected",
                    "description": "5 cases in Kambia district",
                    "confidence": 0.85,
                    "evidence": {"case_count": 5},
                }]
            }
        ])
        adapter = MockDataAdapter({
            "Condition": [
                {"id": "1", "code": "A00.1", "case_count": 5},
                {"id": "2", "code": "A00.1", "case_count": 5},
            ]
        })
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            site_id="site-1",
        )
        alerts = await agent._run_skill(DummySkill(), event)

        assert len(alerts) >= 1
        alert = alerts[0]
        assert alert.ai_generated is True
        assert alert.ai_model == "mock-model"
        assert alert.requires_review is True
        assert alert.reflection_iterations >= 0

        await agent.stop()

    async def test_run_rule_path_degraded(self, config):
        llm = MockLLMEngine(is_available=False)
        adapter = MockDataAdapter({
            "Condition": [{"id": str(i)} for i in range(10)]
        })
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            site_id="site-1",
        )
        alerts = await agent._run_rule_path(DummySkill(), event)

        assert len(alerts) == 1
        assert alerts[0].ai_generated is False
        assert alerts[0].rule_validated is True
        assert "rule-based" in alerts[0].ai_reasoning.lower()
        assert alerts[0].requires_review is True

        await agent.stop()

    async def test_handle_event_routes_correctly(self, config):
        llm = MockLLMEngine(responses=[
            {"findings": [{"severity": "moderate", "title": "Test", "confidence": 0.8}]}
        ])
        adapter = MockDataAdapter({"Condition": [{"id": "1"}]})
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            site_id="site-1",
        )
        await agent._handle_event(event)

        # Check that skill.completed was emitted
        completed = [e for e in agent.events.history if e["event"] == "skill.completed"]
        assert len(completed) == 1

        await agent.stop()

    async def test_handle_event_no_match(self, config):
        llm = MockLLMEngine()
        adapter = MockDataAdapter()
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="UnknownType",
        )
        await agent._handle_event(event)

        # No skill.completed events
        completed = [e for e in agent.events.history if e["event"] == "skill.completed"]
        assert len(completed) == 0

        await agent.stop()

    async def test_feedback_processing(self, config):
        llm = MockLLMEngine()
        adapter = MockDataAdapter()
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        alert = Alert(skill_name="dummy-skill", title="Test")
        await agent.memory.store_alert(alert)

        await agent.process_feedback(alert.id, "dismissed", "False alarm")

        threshold = await agent.memory.get_skill_state("dummy-skill", "confidence_threshold")
        assert threshold == 0.65

        await agent.stop()

    async def test_ai_provenance_fields(self, config):
        llm = MockLLMEngine(responses=[
            {
                "findings": [{
                    "severity": "critical",
                    "title": "Outbreak",
                    "confidence": 0.92,
                }]
            }
        ])
        adapter = MockDataAdapter({"Condition": [{"id": "1"}]})
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(event_type="resource.created", resource_type="Condition", site_id="s1")
        alerts = await agent._run_skill(DummySkill(), event)

        assert len(alerts) >= 1
        a = alerts[0]
        assert a.ai_generated is True
        assert a.ai_model is not None
        assert a.ai_confidence is not None
        assert isinstance(a.reflection_iterations, int)
        assert a.requires_review is True

        await agent.stop()
