"""Tests for SqliteAdapter."""

from datetime import datetime, timezone

import pytest

from open_sentinel.adapters.sqlite_adapter import SqliteAdapter


@pytest.fixture
async def adapter():
    """Create an in-memory SQLite adapter with test data."""
    ad = SqliteAdapter(
        db_path=":memory:",
        resource_type_table_map={"Condition": "conditions"},
        time_column="recorded_date",
    )
    await ad.initialize()

    # Create table and insert test data
    now = datetime.now(timezone.utc).isoformat()
    assert ad._db is not None
    await ad._db.executescript(
        """
        CREATE TABLE conditions (
            id TEXT PRIMARY KEY,
            code TEXT,
            site_id TEXT,
            recorded_date TEXT,
            value REAL
        );
        """
    )
    await ad._db.executemany(
        "INSERT INTO conditions VALUES (?, ?, ?, ?, ?)",
        [
            ("1", "A00.1", "clinic-01", now, 5),
            ("2", "A00.0", "clinic-02", now, 3),
            ("3", "B05.1", "clinic-01", now, 2),
            ("4", "A00.9", "clinic-01", "2020-01-01T00:00:00+00:00", 1),
        ],
    )
    await ad._db.commit()

    yield ad
    await ad.close()


class TestSqliteAdapterQuery:
    async def test_query_all(self, adapter):
        rows = await adapter.query("Condition", {})
        assert len(rows) == 4

    async def test_query_with_filter(self, adapter):
        rows = await adapter.query("Condition", {"site_id": "clinic-01"})
        assert len(rows) == 3

    async def test_query_with_code_prefix(self, adapter):
        rows = await adapter.query("Condition", {"code_prefix": "A00"})
        assert len(rows) == 3

    async def test_query_with_list_filter(self, adapter):
        rows = await adapter.query("Condition", {"code": ["A00.1", "A00.0"]})
        assert len(rows) == 2

    async def test_query_with_limit(self, adapter):
        rows = await adapter.query("Condition", {}, limit=2)
        assert len(rows) == 2

    async def test_query_with_time_window(self, adapter):
        rows = await adapter.query("Condition", {"time_window": "4w"})
        assert len(rows) == 3  # old 2020 row filtered out

    async def test_query_empty(self, adapter):
        rows = await adapter.query("Condition", {"code": "NONEXISTENT"})
        assert rows == []

    async def test_query_unknown_resource(self, adapter):
        with pytest.raises(ValueError, match="Unknown resource type"):
            await adapter.query("Observation", {})


class TestSqliteAdapterCount:
    async def test_count_all(self, adapter):
        assert await adapter.count("Condition", {}) == 4

    async def test_count_filtered(self, adapter):
        assert await adapter.count("Condition", {"site_id": "clinic-02"}) == 1

    async def test_count_with_time_window(self, adapter):
        assert await adapter.count("Condition", {"time_window": "4w"}) == 3


class TestSqliteAdapterAggregate:
    async def test_aggregate_count(self, adapter):
        results = await adapter.aggregate("Condition", ["site_id"], "count", {})
        by_site = {r["site_id"]: r["value"] for r in results}
        assert by_site["clinic-01"] == 3
        assert by_site["clinic-02"] == 1

    async def test_aggregate_sum(self, adapter):
        results = await adapter.aggregate("Condition", ["site_id"], "sum", {})
        by_site = {r["site_id"]: r["value"] for r in results}
        assert by_site["clinic-01"] == 8.0
        assert by_site["clinic-02"] == 3.0

    async def test_aggregate_avg(self, adapter):
        results = await adapter.aggregate(
            "Condition", ["site_id"], "avg", {"code_prefix": "A00"}
        )
        by_site = {r["site_id"]: r["value"] for r in results}
        assert by_site["clinic-01"] == 3.0  # (5 + 1) / 2
        assert by_site["clinic-02"] == 3.0

    async def test_aggregate_unsupported_metric(self, adapter):
        with pytest.raises(ValueError, match="Unsupported metric"):
            await adapter.aggregate("Condition", ["site_id"], "median", {})


class TestSqliteAdapterMeta:
    def test_name(self, adapter):
        assert adapter.name() == "sqlite"

    def test_supports_aggregate(self, adapter):
        assert adapter.supports("aggregate") is True

    def test_does_not_support_subscribe(self, adapter):
        assert adapter.supports("subscribe") is False

    def test_has_resource_type(self, adapter):
        assert adapter.has_resource_type("Condition") is True
        assert adapter.has_resource_type("Observation") is False


class TestSqliteAdapterSubscribe:
    async def test_subscribe_yields_sync_events(self, adapter):
        events = []
        async for event in adapter.subscribe(["sync.completed"]):
            events.append(event)
            if len(events) >= 1:
                break
        assert events[0].event_type == "sync.completed"
        assert events[0].resource_type == "Condition"
