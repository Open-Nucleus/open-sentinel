"""Tests for Deduplicator."""

import pytest

from open_sentinel.dedup import Deduplicator
from open_sentinel.memory import SqliteMemoryStore
from open_sentinel.types import Alert


@pytest.fixture
async def memory():
    store = SqliteMemoryStore(":memory:")
    await store.initialize()
    yield store
    await store.close()


class TestDeduplicator:
    async def test_no_dedup_key_passes(self, memory):
        dedup = Deduplicator(memory)
        alerts = [Alert(skill_name="test", title="No key")]
        result = await dedup.deduplicate(alerts)
        assert len(result) == 1

    async def test_duplicate_filtered(self, memory):
        # Store an existing alert with dedup_key
        existing = Alert(skill_name="test", dedup_key="cholera-site1-2024w05")
        await memory.store_alert(existing)

        dedup = Deduplicator(memory)
        new_alert = Alert(skill_name="test", dedup_key="cholera-site1-2024w05")
        result = await dedup.deduplicate([new_alert])
        assert len(result) == 0

    async def test_different_key_passes(self, memory):
        existing = Alert(skill_name="test", dedup_key="key-a")
        await memory.store_alert(existing)

        dedup = Deduplicator(memory)
        new_alert = Alert(skill_name="test", dedup_key="key-b")
        result = await dedup.deduplicate([new_alert])
        assert len(result) == 1

    async def test_mixed_alerts(self, memory):
        existing = Alert(skill_name="test", dedup_key="dup-key")
        await memory.store_alert(existing)

        dedup = Deduplicator(memory)
        alerts = [
            Alert(skill_name="test", dedup_key="dup-key", title="Duplicate"),
            Alert(skill_name="test", title="No key"),
            Alert(skill_name="test", dedup_key="new-key", title="New"),
        ]
        result = await dedup.deduplicate(alerts)
        assert len(result) == 2
        titles = [a.title for a in result]
        assert "No key" in titles
        assert "New" in titles
