"""Tests for SqliteMemoryStore."""

from datetime import datetime, timedelta, timezone

import pytest

from open_sentinel.memory import SqliteMemoryStore
from open_sentinel.types import Alert, Episode


@pytest.fixture
async def memory():
    store = SqliteMemoryStore(":memory:")
    await store.initialize()
    yield store
    await store.close()


class TestWorkingMemory:
    async def test_get_set(self, memory):
        await memory.set_working("key1", {"data": 42})
        result = await memory.get_working("key1")
        assert result == {"data": 42}

    async def test_get_missing(self, memory):
        result = await memory.get_working("nonexistent")
        assert result is None

    async def test_clear(self, memory):
        await memory.set_working("k1", "v1")
        await memory.set_working("k2", "v2")
        await memory.clear_working()
        assert await memory.get_working("k1") is None
        assert await memory.get_working("k2") is None


class TestEpisodicMemory:
    async def test_store_and_recall(self, memory):
        ep = Episode(
            skill_name="cholera",
            site_id="site-1",
            trigger="event",
            findings_summary="5 cases detected",
            alerts_generated=1,
            related_alert_ids=["alert-1"],
        )
        await memory.store_episode(ep)
        episodes = await memory.recall_episodes("cholera", "site-1")
        assert len(episodes) == 1
        assert episodes[0].findings_summary == "5 cases detected"
        assert episodes[0].related_alert_ids == ["alert-1"]

    async def test_recall_limit(self, memory):
        for i in range(10):
            ep = Episode(skill_name="test", site_id="s1", findings_summary=f"ep-{i}")
            await memory.store_episode(ep)
        episodes = await memory.recall_episodes("test", "s1", limit=3)
        assert len(episodes) == 3

    async def test_recall_filters_by_skill_and_site(self, memory):
        await memory.store_episode(Episode(skill_name="a", site_id="s1"))
        await memory.store_episode(Episode(skill_name="b", site_id="s1"))
        await memory.store_episode(Episode(skill_name="a", site_id="s2"))
        episodes = await memory.recall_episodes("a", "s1")
        assert len(episodes) == 1

    async def test_update_episode_outcome(self, memory):
        ep = Episode(
            skill_name="test",
            site_id="s1",
            related_alert_ids=["alert-xyz"],
        )
        await memory.store_episode(ep)
        await memory.update_episode_outcome("alert-xyz", "confirmed", "Looks correct")
        episodes = await memory.recall_episodes("test", "s1")
        assert episodes[0].outcome == "confirmed"
        assert episodes[0].clinician_feedback == "Looks correct"


class TestSemanticMemory:
    async def test_get_set_baseline(self, memory):
        await memory.update_baseline("cholera", "site-1", "weekly_cases", 12.5)
        val = await memory.get_baseline("cholera", "site-1", "weekly_cases")
        assert val == 12.5

    async def test_get_missing_baseline(self, memory):
        val = await memory.get_baseline("x", "y", "z")
        assert val is None

    async def test_update_overwrites(self, memory):
        await memory.update_baseline("s", "s1", "m", 10.0)
        await memory.update_baseline("s", "s1", "m", 20.0)
        val = await memory.get_baseline("s", "s1", "m")
        assert val == 20.0


class TestProceduralMemory:
    async def test_get_set_skill_state(self, memory):
        await memory.set_skill_state("cholera", "confidence_threshold", 0.65)
        val = await memory.get_skill_state("cholera", "confidence_threshold")
        assert val == 0.65

    async def test_get_missing(self, memory):
        val = await memory.get_skill_state("x", "y")
        assert val is None

    async def test_complex_value(self, memory):
        await memory.set_skill_state("s", "config", {"a": 1, "b": [2, 3]})
        val = await memory.get_skill_state("s", "config")
        assert val == {"a": 1, "b": [2, 3]}


class TestAlertHistory:
    async def test_store_and_get(self, memory):
        alert = Alert(
            skill_name="cholera",
            severity="critical",
            title="Outbreak detected",
            ai_generated=True,
            ai_confidence=0.9,
        )
        await memory.store_alert(alert)
        retrieved = await memory.get_alert(alert.id)
        assert retrieved is not None
        assert retrieved.title == "Outbreak detected"
        assert retrieved.ai_confidence == 0.9
        assert retrieved.requires_review is True

    async def test_get_missing(self, memory):
        result = await memory.get_alert("nonexistent")
        assert result is None

    async def test_recent_alerts(self, memory):
        for i in range(5):
            await memory.store_alert(Alert(skill_name="test", title=f"Alert {i}"))
        alerts = await memory.recent_alerts("test", limit=3)
        assert len(alerts) == 3

    async def test_update_outcome(self, memory):
        alert = Alert(skill_name="test", title="To review")
        await memory.store_alert(alert)
        await memory.update_alert_outcome(alert.id, "confirmed", "Correct finding")
        updated = await memory.get_alert(alert.id)
        assert updated.outcome == "confirmed"
        assert updated.clinician_feedback == "Correct finding"

    async def test_count_recent(self, memory):
        await memory.store_alert(Alert(skill_name="s1", severity="critical"))
        await memory.store_alert(Alert(skill_name="s1", severity="critical"))
        await memory.store_alert(Alert(skill_name="s1", severity="high"))
        count = await memory.count_recent_alerts("s1", severity="critical")
        assert count == 2
        count_all = await memory.count_recent_alerts("s1")
        assert count_all == 3


class TestEmissionQueue:
    async def test_queue_and_get(self, memory):
        await memory.queue_emission("alert-1", "webhook", '{"url": "http://..."}')
        pending = await memory.get_pending_emissions()
        assert len(pending) == 1
        assert pending[0]["alert_id"] == "alert-1"

    async def test_mark_complete(self, memory):
        await memory.queue_emission("a1", "webhook", "{}")
        pending = await memory.get_pending_emissions()
        await memory.mark_emission_complete(pending[0]["id"])
        pending = await memory.get_pending_emissions()
        assert len(pending) == 0

    async def test_mark_failed_with_retry(self, memory):
        await memory.queue_emission("a1", "sms", "{}")
        pending = await memory.get_pending_emissions()
        eid = pending[0]["id"]
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await memory.mark_emission_failed(eid, future)
        # Should not appear in pending yet (next_retry is in the future)
        pending = await memory.get_pending_emissions()
        assert len(pending) == 0
