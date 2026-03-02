"""Tests for SkillTestHarness — three spec test patterns."""

from typing import Dict, List, Optional

from open_sentinel.interfaces import Skill
from open_sentinel.llm.mock import MockLLMEngine
from open_sentinel.testing.fixtures import make_data_event
from open_sentinel.testing.harness import SkillTestHarness
from open_sentinel.types import (
    AgentConfig,
    Alert,
    AnalysisContext,
    DataRequirement,
    Priority,
)


class CholeraSkill(Skill):
    """Test skill mimicking cholera surveillance."""

    def name(self) -> str:
        return "idsr-cholera"

    def priority(self) -> Priority:
        return Priority.CRITICAL

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "cases": DataRequirement(
                resource_type="Condition",
                filters={"code": "A00"},
                time_window="4w",
            ),
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        cases = ctx.data.get("cases", [])
        return f"Analyze {len(cases)} cholera cases for outbreak patterns."

    def goal(self) -> str:
        return "Detect cholera outbreaks"

    def response_schema(self) -> Optional[Dict]:
        return {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "confidence": {"type": "number"},
                            "evidence": {"type": "object"},
                        },
                    },
                },
            },
        }

    def critique_findings(self, findings: List[Dict], ctx: AnalysisContext) -> str:
        cases = ctx.data.get("cases", [])
        for finding in findings:
            evidence = finding.get("evidence", {})
            claimed_count = evidence.get("case_count")
            if claimed_count is not None and claimed_count > len(cases):
                return f"Claimed {claimed_count} cases but only {len(cases)} in data"
        return "ACCEPT"

    def max_reflections(self) -> int:
        return 2

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        cases = ctx.data.get("cases", [])
        if len(cases) >= 3:
            return [Alert(
                skill_name=self.name(),
                severity="critical",
                title="Cholera threshold exceeded",
                description=f"{len(cases)} cases in 4-week window (threshold: 3)",
                measured_value=float(len(cases)),
                threshold_value=3.0,
                category="epidemic",
            )]
        return []


class TestPattern1LLMWithReflection:
    """Pattern 1: LLM path with reflection validation."""

    async def test_llm_analysis_with_reflection(self):
        llm = MockLLMEngine(responses=[
            {
                "findings": [{
                    "severity": "critical",
                    "title": "Cholera outbreak detected",
                    "description": "5 confirmed cases in Kambia",
                    "confidence": 0.9,
                    "evidence": {"case_count": 5},
                }]
            }
        ])

        harness = SkillTestHarness(
            skill=CholeraSkill(),
            llm=llm,
            config=AgentConfig(state_db_path=":memory:", hardware="hub_16gb"),
        )
        harness.set_data({
            "cases": [
                {"id": str(i), "code": "A00.1", "case_count": 5}
                for i in range(5)
            ],
        })
        harness.set_site_id("kambia")

        result = await harness.run_async()

        assert not result.degraded
        assert len(result.alerts) >= 1
        alert = result.alerts[0]
        assert alert.ai_generated is True
        assert alert.requires_review is True
        assert alert.severity == "critical"
        assert alert.ai_confidence is not None


class TestPattern2HallucinationDetection:
    """Pattern 2: LLM fabricates data, reflection catches it."""

    async def test_hallucination_caught_by_reflection(self):
        llm = MockLLMEngine(responses=[
            # First response: LLM claims 20 cases but only 2 in data
            {
                "findings": [{
                    "severity": "critical",
                    "title": "Massive outbreak",
                    "description": "20 confirmed cases",
                    "confidence": 0.95,
                    "evidence": {"case_count": 20},
                }]
            },
            # After reflection: corrected
            {
                "findings": [{
                    "severity": "moderate",
                    "title": "Low case count",
                    "description": "2 cases observed",
                    "confidence": 0.7,
                    "evidence": {"case_count": 2},
                }]
            },
        ])

        harness = SkillTestHarness(
            skill=CholeraSkill(),
            llm=llm,
            config=AgentConfig(state_db_path=":memory:", hardware="hub_16gb"),
        )
        harness.set_data({
            "cases": [{"id": "1", "case_count": 2}, {"id": "2", "case_count": 2}],
        })

        result = await harness.run_async()

        # Reflection should have triggered
        assert result.reflection_count >= 1
        # The reflect call should have been made
        assert any(c["method"] == "reflect" for c in llm.call_history)


class TestPattern3DegradedMode:
    """Pattern 3: No LLM, rules-only fallback."""

    async def test_degraded_mode_rules_only(self):
        llm = MockLLMEngine(is_available=False)

        harness = SkillTestHarness(
            skill=CholeraSkill(),
            llm=llm,
            config=AgentConfig(state_db_path=":memory:"),
        )
        harness.set_data({
            "cases": [{"id": str(i)} for i in range(5)],
        })

        result = await harness.run_async()

        assert result.degraded is True
        assert result.reflection_count == 0
        assert len(result.alerts) == 1
        alert = result.alerts[0]
        assert alert.ai_generated is False
        assert alert.rule_validated is True
        assert alert.requires_review is True
        assert alert.severity == "critical"

    async def test_degraded_below_threshold(self):
        llm = MockLLMEngine(is_available=False)

        harness = SkillTestHarness(
            skill=CholeraSkill(),
            llm=llm,
            config=AgentConfig(state_db_path=":memory:"),
        )
        harness.set_data({
            "cases": [{"id": "1"}, {"id": "2"}],
        })

        result = await harness.run_async()

        assert result.degraded is True
        assert len(result.alerts) == 0

    async def test_forced_degraded_mode(self):
        llm = MockLLMEngine(is_available=True)

        harness = SkillTestHarness(
            skill=CholeraSkill(),
            llm=llm,
            config=AgentConfig(state_db_path=":memory:"),
        )
        harness.set_data({"cases": [{"id": str(i)} for i in range(5)]})

        result = await harness.run_async(degraded=True)
        assert result.degraded is True
        assert len(result.alerts) == 1


class TestHarnessAPI:
    async def test_set_data_chaining(self):
        harness = SkillTestHarness(skill=CholeraSkill())
        result = harness.set_data({"cases": []}).set_site_id("test")
        assert result is harness

    async def test_fixtures_integration(self):
        event = make_data_event(resource_type="Condition")
        harness = SkillTestHarness(
            skill=CholeraSkill(),
            llm=MockLLMEngine(responses=[{"findings": []}]),
        )
        harness.set_trigger_event(event)
        harness.set_data({"cases": []})
        result = await harness.run_async()
        assert result.degraded is False
