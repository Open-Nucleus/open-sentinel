"""Tests for CsvAdapter."""

from datetime import datetime, timezone

import pytest

from open_sentinel.adapters.csv_adapter import CsvAdapter


@pytest.fixture
def csv_dir(tmp_path):
    """Create a tmp directory with test CSV files."""
    conditions = tmp_path / "conditions.csv"
    now = datetime.now(timezone.utc)
    # Write dates in ISO format for string comparison
    conditions.write_text(
        "id,code,site_id,date,value\n"
        f"1,A00.1,clinic-01,{now.isoformat()},5\n"
        f"2,A00.0,clinic-02,{now.isoformat()},3\n"
        f"3,B05.1,clinic-01,{now.isoformat()},2\n"
        "4,A00.9,clinic-01,2020-01-01T00:00:00+00:00,1\n"
    )
    return tmp_path


@pytest.fixture
def adapter(csv_dir):
    return CsvAdapter(
        directory=str(csv_dir),
        resource_type_file_map={"Condition": "conditions.csv"},
        time_column="date",
    )


class TestCsvAdapterQuery:
    async def test_query_all(self, adapter):
        rows = await adapter.query("Condition", {})
        assert len(rows) == 4

    async def test_query_with_filter(self, adapter):
        rows = await adapter.query("Condition", {"site_id": "clinic-01"})
        assert len(rows) == 3
        assert all(r["site_id"] == "clinic-01" for r in rows)

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
        # The old row (2020-01-01) should be filtered out
        assert len(rows) == 3

    async def test_query_empty_result(self, adapter):
        rows = await adapter.query("Condition", {"code": "NONEXISTENT"})
        assert rows == []

    async def test_query_missing_resource_type(self, adapter):
        rows = await adapter.query("Observation", {})
        assert rows == []


class TestCsvAdapterCount:
    async def test_count_all(self, adapter):
        assert await adapter.count("Condition", {}) == 4

    async def test_count_filtered(self, adapter):
        assert await adapter.count("Condition", {"site_id": "clinic-02"}) == 1


class TestCsvAdapterAggregate:
    async def test_aggregate_count(self, adapter):
        results = await adapter.aggregate("Condition", ["site_id"], "count", {})
        by_site = {r["site_id"]: r["value"] for r in results}
        assert by_site["clinic-01"] == 3
        assert by_site["clinic-02"] == 1

    async def test_aggregate_sum(self, adapter):
        results = await adapter.aggregate("Condition", ["site_id"], "sum", {})
        by_site = {r["site_id"]: r["value"] for r in results}
        assert by_site["clinic-01"] == 8.0  # 5 + 2 + 1
        assert by_site["clinic-02"] == 3.0

    async def test_aggregate_avg(self, adapter):
        results = await adapter.aggregate(
            "Condition", ["site_id"], "avg", {"code_prefix": "A00"}
        )
        by_site = {r["site_id"]: r["value"] for r in results}
        assert by_site["clinic-01"] == 3.0  # (5 + 1) / 2
        assert by_site["clinic-02"] == 3.0


class TestCsvAdapterMeta:
    def test_name(self, adapter):
        assert adapter.name() == "csv"

    def test_supports_aggregate(self, adapter):
        assert adapter.supports("aggregate") is True

    def test_does_not_support_subscribe(self, adapter):
        assert adapter.supports("subscribe") is False

    def test_has_resource_type(self, adapter):
        assert adapter.has_resource_type("Condition") is True
        assert adapter.has_resource_type("Observation") is False


class TestCsvAdapterSubscribe:
    async def test_subscribe_yields_sync_events(self, adapter):
        events = []
        async for event in adapter.subscribe(["sync.completed"]):
            events.append(event)
            if len(events) >= 1:
                break
        assert events[0].event_type == "sync.completed"
        assert events[0].resource_type == "Condition"
