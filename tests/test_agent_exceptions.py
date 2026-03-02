"""Tests for agent exception handling: LLM timeout and adapter retry."""

import asyncio
from typing import AsyncIterator, Dict, List

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
    def __init__(self, data=None, fail_count=0):
        self._data = data or {}
        self._fail_count = fail_count
        self._call_count = 0

    def name(self) -> str:
        return "mock"

    async def query(self, resource_type, filters, limit=None):
        self._call_count += 1
        if self._call_count <= self._fail_count:
            raise ConnectionError(f"Fetch failed (attempt {self._call_count})")
        result = self._data.get(resource_type, [])
        return result[:limit] if limit else result

    async def count(self, resource_type, filters):
        return len(self._data.get(resource_type, []))

    async def subscribe(self, event_types) -> AsyncIterator[DataEvent]:
        return
        yield  # make it an async generator

    async def aggregate(self, resource_type, group_by, metric, filters):
        return self._data.get(resource_type, [])


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
        return f"Analyze {count} conditions."

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        conditions = ctx.data.get("conditions", [])
        if len(conditions) > 0:
            return [Alert(
                skill_name=self.name(),
                severity="high",
                title="Rule-based detection",
                measured_value=float(len(conditions)),
                rule_validated=True,
            )]
        return []


class SlowLLMEngine(MockLLMEngine):
    """LLM engine that simulates slow response times."""

    def __init__(self, delay_seconds: float = 5.0, **kwargs):
        super().__init__(**kwargs)
        self._delay = delay_seconds

    async def reason(self, system_prompt, clinical_context, question, schema=None):
        self.call_history.append({"method": "reason"})
        await asyncio.sleep(self._delay)
        return self._make_llm_response(self._next_response())


@pytest.fixture
def config():
    return AgentConfig(state_db_path=":memory:", hardware="hub_16gb", llm_timeout_seconds=1)


class TestLLMTimeout:
    async def test_timeout_falls_back_to_rule_path(self, config):
        llm = SlowLLMEngine(
            delay_seconds=5.0,
            responses=[
                {"findings": [{"severity": "high", "title": "LLM finding", "confidence": 0.9}]}
            ],
        )
        adapter = MockDataAdapter({"Condition": [{"id": "1"}, {"id": "2"}]})
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            site_id="site-1",
        )
        alerts = await agent._run_skill(DummySkill(), event)

        # Should have fallen back to rule path
        assert len(alerts) >= 1
        assert alerts[0].ai_generated is False
        assert alerts[0].rule_validated is True

        # Verify llm.timeout event was emitted
        timeout_events = [e for e in agent.events.history if e["event"] == "llm.timeout"]
        assert len(timeout_events) >= 1

        await agent.stop()

    async def test_fast_llm_does_not_timeout(self, config):
        config.llm_timeout_seconds = 60  # very generous timeout
        llm = MockLLMEngine(
            responses=[
                {"findings": [{"severity": "high", "title": "LLM result", "confidence": 0.8}]}
            ],
        )
        adapter = MockDataAdapter({"Condition": [{"id": "1"}]})
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            site_id="site-1",
        )
        alerts = await agent._run_skill(DummySkill(), event)

        assert len(alerts) >= 1
        assert alerts[0].ai_generated is True

        await agent.stop()


class TestAdapterRetry:
    async def test_retry_succeeds_after_failures(self, config):
        # Fail first 2 attempts, succeed on 3rd
        adapter = MockDataAdapter(
            data={"Condition": [{"id": "1"}, {"id": "2"}]},
            fail_count=2,
        )
        llm = MockLLMEngine(is_available=False)
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            site_id="site-1",
        )

        # _fetch_data should retry and succeed
        req = DataRequirement(resource_type="Condition")
        result = await agent._fetch_data(req, event)
        assert len(result) == 2

        # Verify retry events were emitted
        retry_events = [e for e in agent.events.history if e["event"] == "data.fetch.retry"]
        assert len(retry_events) == 2

        await agent.stop()

    async def test_retry_all_attempts_fail(self, config):
        # All 3 attempts fail
        adapter = MockDataAdapter(
            data={"Condition": [{"id": "1"}]},
            fail_count=5,  # More than max_attempts (3)
        )
        llm = MockLLMEngine(is_available=False)
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            site_id="site-1",
        )

        req = DataRequirement(resource_type="Condition")
        with pytest.raises(ConnectionError):
            await agent._fetch_data(req, event)

        # Verify failed event was emitted
        failed_events = [e for e in agent.events.history if e["event"] == "data.fetch.failed"]
        assert len(failed_events) == 1

        await agent.stop()

    async def test_fetch_all_data_handles_failure_gracefully(self, config):
        # _fetch_all_data should return [] for failed requirements
        adapter = MockDataAdapter(
            data={"Condition": [{"id": "1"}]},
            fail_count=5,
        )
        llm = MockLLMEngine(is_available=False)
        agent = SentinelAgent(adapter, llm, [DummySkill()], [ConsoleOutput()], config)
        await agent.start()

        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            site_id="site-1",
        )

        data = await agent._fetch_all_data(DummySkill(), event)
        # Should get empty list due to failure
        assert data["conditions"] == []

        await agent.stop()
