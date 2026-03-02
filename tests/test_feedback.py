"""Tests for FeedbackProcessor."""

import pytest

from open_sentinel.events import EventBus
from open_sentinel.feedback import FeedbackProcessor
from open_sentinel.memory import SqliteMemoryStore
from open_sentinel.types import Alert


@pytest.fixture
async def memory():
    store = SqliteMemoryStore(":memory:")
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def events():
    return EventBus()


class TestFeedbackProcessor:
    async def test_dismissed_raises_threshold(self, memory, events):
        processor = FeedbackProcessor(memory, events)
        alert = Alert(skill_name="cholera", title="False positive")
        await memory.store_alert(alert)

        await processor.process_feedback(alert.id, "dismissed", "Not real")

        threshold = await memory.get_skill_state("cholera", "confidence_threshold")
        assert threshold == 0.65  # default 0.6 + 0.05

    async def test_multiple_dismissals(self, memory, events):
        processor = FeedbackProcessor(memory, events)
        alert1 = Alert(skill_name="cholera")
        alert2 = Alert(skill_name="cholera")
        await memory.store_alert(alert1)
        await memory.store_alert(alert2)

        await processor.process_feedback(alert1.id, "dismissed")
        await processor.process_feedback(alert2.id, "dismissed")

        threshold = await memory.get_skill_state("cholera", "confidence_threshold")
        assert abs(threshold - 0.7) < 1e-9  # 0.6 + 0.05 + 0.05

    async def test_threshold_ceiling(self, memory, events):
        processor = FeedbackProcessor(memory, events)
        await memory.set_skill_state("cholera", "confidence_threshold", 0.93)
        alert = Alert(skill_name="cholera")
        await memory.store_alert(alert)

        await processor.process_feedback(alert.id, "dismissed")

        threshold = await memory.get_skill_state("cholera", "confidence_threshold")
        assert threshold == 0.95  # capped

    async def test_confirmed_sets_last_confirmed(self, memory, events):
        processor = FeedbackProcessor(memory, events)
        alert = Alert(skill_name="measles")
        await memory.store_alert(alert)

        await processor.process_feedback(alert.id, "confirmed", "Correct finding")

        last_confirmed = await memory.get_skill_state("measles", "last_confirmed")
        assert last_confirmed is not None

    async def test_emits_reviewed_event(self, memory, events):
        processor = FeedbackProcessor(memory, events)
        alert = Alert(skill_name="test")
        await memory.store_alert(alert)

        received = []
        events.subscribe("alert.reviewed", lambda e: received.append(e))

        await processor.process_feedback(alert.id, "confirmed")
        assert len(received) == 1
        assert received[0]["alert_id"] == alert.id
        assert received[0]["outcome"] == "confirmed"

    async def test_emits_calibrated_event(self, memory, events):
        processor = FeedbackProcessor(memory, events)
        alert = Alert(skill_name="test")
        await memory.store_alert(alert)

        received = []
        events.subscribe("skill.calibrated", lambda e: received.append(e))

        await processor.process_feedback(alert.id, "dismissed")
        assert len(received) == 1
        assert received[0]["reason"] == "false_positive"

    async def test_missing_alert_no_error(self, memory, events):
        processor = FeedbackProcessor(memory, events)
        await processor.process_feedback("nonexistent", "confirmed")
