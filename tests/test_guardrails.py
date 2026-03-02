"""Tests for GuardrailPipeline."""

import pytest

from open_sentinel.events import EventBus
from open_sentinel.guardrails import GuardrailPipeline, _evidence_exists_in_data
from open_sentinel.memory import SqliteMemoryStore
from open_sentinel.types import Alert, AnalysisContext


@pytest.fixture
async def memory():
    store = SqliteMemoryStore(":memory:")
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def events():
    return EventBus()


def _make_ctx(**kwargs) -> AnalysisContext:
    defaults = {"trigger": "event", "data": {}}
    defaults.update(kwargs)
    return AnalysisContext(**defaults)


class TestConfidenceGating:
    async def test_passes_above_threshold(self, memory, events):
        pipeline = GuardrailPipeline(memory, events)
        alert = Alert(ai_generated=True, ai_confidence=0.8, title="Good")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 1

    async def test_gates_below_threshold(self, memory, events):
        pipeline = GuardrailPipeline(memory, events)
        alert = Alert(ai_generated=True, ai_confidence=0.3, title="Low conf")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 0

    async def test_uses_calibrated_threshold(self, memory, events):
        await memory.set_skill_state("test-skill", "confidence_threshold", 0.9)
        pipeline = GuardrailPipeline(memory, events)
        alert = Alert(ai_generated=True, ai_confidence=0.85, title="Below cal")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 0

    async def test_non_ai_passes(self, memory, events):
        pipeline = GuardrailPipeline(memory, events)
        alert = Alert(ai_generated=False, title="Rule-based")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 1

    async def test_no_confidence_passes(self, memory, events):
        pipeline = GuardrailPipeline(memory, events)
        alert = Alert(ai_generated=True, ai_confidence=None, title="No conf")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 1


class TestHallucinationDetection:
    async def test_valid_evidence_passes(self, memory, events):
        pipeline = GuardrailPipeline(memory, events)
        alert = Alert(
            ai_generated=True,
            ai_confidence=0.9,
            evidence={"case_count": 5},
            title="Valid",
        )
        ctx = _make_ctx(data={"cases": [{"case_count": 5}]})
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 1

    async def test_hallucinated_evidence_gated(self, memory, events):
        pipeline = GuardrailPipeline(memory, events)
        alert = Alert(
            ai_generated=True,
            ai_confidence=0.9,
            evidence={"nonexistent_field": 99},
            title="Hallucinated",
        )
        ctx = _make_ctx(data={"cases": [{"actual_field": 1}]})
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 0


class TestRateLimiting:
    async def test_within_limit(self, memory, events):
        pipeline = GuardrailPipeline(memory, events, max_critical_per_hour=5)
        alert = Alert(severity="critical", title="Crit1")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 1

    async def test_exceeds_limit(self, memory, events):
        pipeline = GuardrailPipeline(memory, events, max_critical_per_hour=2)
        # Pre-fill critical alerts
        for _ in range(2):
            await memory.store_alert(Alert(skill_name="test-skill", severity="critical"))
        alert = Alert(severity="critical", title="Over limit")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 0

    async def test_non_critical_not_limited(self, memory, events):
        pipeline = GuardrailPipeline(memory, events, max_critical_per_hour=0)
        alert = Alert(severity="high", title="High")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert len(result) == 1


class TestRequiresReview:
    async def test_always_true(self, memory, events):
        pipeline = GuardrailPipeline(memory, events)
        alert = Alert(title="Test")
        ctx = _make_ctx()
        result = await pipeline.apply([alert], ctx, "test-skill")
        assert all(a.requires_review is True for a in result)


class TestEvidenceExistsInData:
    def test_empty_evidence(self):
        assert _evidence_exists_in_data({}, {"x": [{"a": 1}]}) is True

    def test_empty_data(self):
        assert _evidence_exists_in_data({"a": 1}, {}) is False

    def test_evidence_found_in_list(self):
        assert _evidence_exists_in_data(
            {"case_count": 5},
            {"cases": [{"case_count": 5}]},
        ) is True

    def test_evidence_not_found(self):
        assert _evidence_exists_in_data(
            {"nonexistent": 99},
            {"cases": [{"actual": 1}]},
        ) is False
