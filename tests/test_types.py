"""Tests for core types."""

from datetime import datetime

from open_sentinel.types import (
    AgentConfig,
    Alert,
    AnalysisContext,
    DataEvent,
    DataRequirement,
    Episode,
    InvestigationPlan,
    InvestigationStep,
    LLMResponse,
    Priority,
    SkillTrigger,
)


class TestPriority:
    def test_ordering(self):
        assert Priority.CRITICAL > Priority.HIGH > Priority.MEDIUM > Priority.LOW

    def test_values(self):
        assert Priority.CRITICAL == 4
        assert Priority.LOW == 1


class TestSkillTrigger:
    def test_values(self):
        assert SkillTrigger.EVENT == "event"
        assert SkillTrigger.SCHEDULE == "schedule"
        assert SkillTrigger.BOTH == "both"
        assert SkillTrigger.MANUAL == "manual"


class TestDataEvent:
    def test_frozen(self):
        evt = DataEvent(event_type="resource.created", resource_type="Condition")
        try:
            evt.event_type = "changed"
            assert False, "Should be frozen"
        except Exception:
            pass

    def test_defaults(self):
        evt = DataEvent(event_type="resource.created", resource_type="Condition")
        assert evt.resource_id is None
        assert evt.site_id is None
        assert isinstance(evt.timestamp, datetime)


class TestAlert:
    def test_requires_review_always_true(self):
        alert = Alert(requires_review=False)
        assert alert.requires_review is True

    def test_requires_review_default(self):
        alert = Alert()
        assert alert.requires_review is True

    def test_uuid_auto_gen(self):
        a1 = Alert()
        a2 = Alert()
        assert a1.id != a2.id
        assert len(a1.id) == 36  # UUID format

    def test_serialization_roundtrip(self):
        alert = Alert(
            skill_name="test-skill",
            severity="critical",
            title="Test Alert",
            ai_generated=True,
            ai_confidence=0.85,
        )
        data = alert.model_dump()
        restored = Alert.model_validate(data)
        assert restored.skill_name == "test-skill"
        assert restored.severity == "critical"
        assert restored.ai_confidence == 0.85
        assert restored.requires_review is True

    def test_json_roundtrip(self):
        alert = Alert(skill_name="test", severity="high")
        json_str = alert.model_dump_json()
        restored = Alert.model_validate_json(json_str)
        assert restored.skill_name == "test"
        assert restored.requires_review is True

    def test_all_fields_present(self):
        fields = set(Alert.model_fields.keys())
        expected = {
            "id", "skill_name", "severity", "category", "title", "description",
            "patient_id", "patient_ids", "site_id", "site_ids",
            "evidence", "threshold", "measured_value", "threshold_value",
            "ai_generated", "ai_confidence", "ai_model", "ai_reasoning",
            "rule_validated", "reflection_iterations", "requires_review",
            "outcome", "clinician_feedback",
            "dedup_key", "fhir_resource_type", "fhir_code",
            "created_at", "reviewed_at",
        }
        assert expected.issubset(fields)


class TestEpisode:
    def test_uuid_auto_gen(self):
        e = Episode()
        assert len(e.id) == 36

    def test_related_alert_ids(self):
        e = Episode(related_alert_ids=["a1", "a2"])
        assert e.related_alert_ids == ["a1", "a2"]


class TestDataRequirement:
    def test_defaults(self):
        req = DataRequirement(resource_type="Condition")
        assert req.filters == {}
        assert req.time_window is None


class TestLLMResponse:
    def test_basic(self):
        resp = LLMResponse(text="hello", model="phi3:mini")
        assert resp.text == "hello"
        assert resp.structured is None
        assert resp.tokens_used == 0


class TestInvestigationPlan:
    def test_with_steps(self):
        step = InvestigationStep(
            description="Check cases",
            analysis_question="How many cases?",
        )
        plan = InvestigationPlan(goal="Investigate outbreak", steps=[step], rationale="test")
        assert len(plan.steps) == 1


class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig()
        assert cfg.hardware == "pi4_8gb"
        assert cfg.max_critical_per_hour == 10
        assert cfg.llm_timeout_seconds == 60


class TestAnalysisContext:
    def test_arbitrary_types(self):
        ctx = AnalysisContext(trigger="event", llm="mock", memory="mock")
        assert ctx.llm == "mock"
