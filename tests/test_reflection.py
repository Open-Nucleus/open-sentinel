"""Tests for ReflectionEngine."""

import json

from open_sentinel.events import EventBus
from open_sentinel.llm.mock import MockLLMEngine
from open_sentinel.reflection import ReflectionEngine, _parse_structured
from open_sentinel.resources import ResourceManager
from open_sentinel.types import AnalysisContext


class _CritiquingSkill:
    """Skill that rejects the first finding, then accepts."""

    def __init__(self, reject_count: int = 1):
        self._reject_count = reject_count
        self._calls = 0

    def name(self) -> str:
        return "critiquing-skill"

    def max_reflections(self) -> int:
        return 3

    def critique_findings(self, findings, ctx):
        self._calls += 1
        if self._calls <= self._reject_count:
            return "Finding lacks supporting evidence"
        return "ACCEPT"


class _AlwaysAcceptSkill:
    def name(self) -> str:
        return "accept-skill"

    def max_reflections(self) -> int:
        return 2

    def critique_findings(self, findings, ctx):
        return "ACCEPT"


def _make_ctx() -> AnalysisContext:
    return AnalysisContext(trigger="event")


class TestReflectionEngine:
    async def test_no_reflection_when_accepted(self):
        rm = ResourceManager("hub_16gb")
        events = EventBus()
        engine = ReflectionEngine(rm, events)
        llm = MockLLMEngine()
        findings = [{"severity": "critical", "title": "Test"}]

        result, count = await engine.run_reflection_loop(
            findings, _AlwaysAcceptSkill(), _make_ctx(), llm, "context"
        )
        assert count == 0
        assert result == findings
        assert len(llm.call_history) == 0

    async def test_one_reflection(self):
        rm = ResourceManager("hub_16gb")
        events = EventBus()
        engine = ReflectionEngine(rm, events)
        llm = MockLLMEngine(responses=[
            {"findings": [{"severity": "critical", "title": "Refined"}]}
        ])
        findings = [{"severity": "critical", "title": "Original"}]

        result, count = await engine.run_reflection_loop(
            findings, _CritiquingSkill(reject_count=1), _make_ctx(), llm, "context"
        )
        assert count == 1
        assert len(llm.call_history) == 1
        assert llm.call_history[0]["method"] == "reflect"

    async def test_capped_by_resource_manager(self):
        rm = ResourceManager("pi4_8gb")  # max_reflections=2
        events = EventBus()
        engine = ReflectionEngine(rm, events)
        llm = MockLLMEngine(responses=[
            {"findings": [{"title": "R1"}]},
            {"findings": [{"title": "R2"}]},
            {"findings": [{"title": "R3"}]},
        ])
        findings = [{"title": "Original"}]

        # Skill wants 3 reflections but resource manager caps at 2
        skill = _CritiquingSkill(reject_count=10)  # always reject
        result, count = await engine.run_reflection_loop(
            findings, skill, _make_ctx(), llm, "context"
        )
        assert count == 2

    async def test_emits_reflecting_events(self):
        rm = ResourceManager("hub_16gb")
        events = EventBus()
        received = []
        events.subscribe("skill.reflecting", lambda e: received.append(e))

        engine = ReflectionEngine(rm, events)
        llm = MockLLMEngine(responses=[{"findings": [{"title": "Refined"}]}])
        findings = [{"title": "Original"}]

        await engine.run_reflection_loop(
            findings, _CritiquingSkill(1), _make_ctx(), llm, "context", run_id="r1"
        )
        assert len(received) == 1
        assert received[0]["run_id"] == "r1"
        assert received[0]["iteration"] == 1


class TestParseStructured:
    def test_json_dict_with_findings(self):
        text = json.dumps({"findings": [{"title": "A"}, {"title": "B"}]})
        result = _parse_structured(text)
        assert len(result) == 2

    def test_json_dict_without_findings(self):
        text = json.dumps({"title": "Single"})
        result = _parse_structured(text)
        assert result == [{"title": "Single"}]

    def test_json_list(self):
        text = json.dumps([{"a": 1}, {"b": 2}])
        result = _parse_structured(text)
        assert len(result) == 2

    def test_plain_text(self):
        result = _parse_structured("not json at all")
        assert result == [{"text": "not json at all"}]
