"""Tests for FhirGitAdapter."""

import json
from datetime import datetime, timezone

import pytest

from open_sentinel.adapters.fhir_git import FhirGitAdapter


@pytest.fixture
async def fhir_adapter(tmp_path):
    """Create a FhirGitAdapter with test JSON files and in-memory index."""
    # Create FHIR JSON files
    fhir_dir = tmp_path / "fhir"
    fhir_dir.mkdir()
    conditions_dir = fhir_dir / "conditions"
    conditions_dir.mkdir()

    now = datetime.now(timezone.utc).isoformat()

    files = [
        ("cond-01.json", {
            "resourceType": "Condition", "id": "cond-01",
            "code": "A00.1", "site_id": "clinic-01",
        }),
        ("cond-02.json", {
            "resourceType": "Condition", "id": "cond-02",
            "code": "A00.0", "site_id": "clinic-02",
        }),
        ("cond-03.json", {
            "resourceType": "Condition", "id": "cond-03",
            "code": "B05.1", "site_id": "clinic-01",
        }),
    ]
    for filename, data in files:
        (conditions_dir / filename).write_text(json.dumps(data))

    adapter = FhirGitAdapter(
        repo_path=str(fhir_dir),
        index_db=":memory:",
    )
    await adapter.initialize()

    # Index the resources
    await adapter.index_resource(
        "conditions/cond-01.json", "Condition",
        code="A00.1", site_id="clinic-01", date=now,
    )
    await adapter.index_resource(
        "conditions/cond-02.json", "Condition",
        code="A00.0", site_id="clinic-02", date=now,
    )
    await adapter.index_resource(
        "conditions/cond-03.json", "Condition",
        code="B05.1", site_id="clinic-01", date=now,
    )

    yield adapter
    await adapter.close()


class TestFhirGitQuery:
    async def test_query_all(self, fhir_adapter):
        rows = await fhir_adapter.query("Condition", {})
        assert len(rows) == 3

    async def test_query_by_site(self, fhir_adapter):
        rows = await fhir_adapter.query("Condition", {"site_id": "clinic-01"})
        assert len(rows) == 2

    async def test_query_by_code(self, fhir_adapter):
        rows = await fhir_adapter.query("Condition", {"code": "A00.1"})
        assert len(rows) == 1
        assert rows[0]["id"] == "cond-01"

    async def test_query_by_code_prefix(self, fhir_adapter):
        rows = await fhir_adapter.query("Condition", {"code_prefix": "A00"})
        assert len(rows) == 2

    async def test_query_with_limit(self, fhir_adapter):
        rows = await fhir_adapter.query("Condition", {}, limit=1)
        assert len(rows) == 1

    async def test_query_no_results(self, fhir_adapter):
        rows = await fhir_adapter.query("Condition", {"code": "NONEXISTENT"})
        assert rows == []

    async def test_query_loads_full_json(self, fhir_adapter):
        rows = await fhir_adapter.query("Condition", {"code": "A00.1"})
        assert rows[0]["resourceType"] == "Condition"
        assert rows[0]["code"] == "A00.1"


class TestFhirGitCount:
    async def test_count_all(self, fhir_adapter):
        assert await fhir_adapter.count("Condition", {}) == 3

    async def test_count_filtered(self, fhir_adapter):
        assert await fhir_adapter.count("Condition", {"site_id": "clinic-02"}) == 1

    async def test_count_with_prefix(self, fhir_adapter):
        assert await fhir_adapter.count("Condition", {"code_prefix": "A00"}) == 2


class TestFhirGitAggregate:
    async def test_aggregate_count(self, fhir_adapter):
        results = await fhir_adapter.aggregate("Condition", ["site_id"], "count", {})
        by_site = {r["site_id"]: r["value"] for r in results}
        assert by_site["clinic-01"] == 2
        assert by_site["clinic-02"] == 1

    async def test_aggregate_count_filtered(self, fhir_adapter):
        results = await fhir_adapter.aggregate(
            "Condition", ["site_id"], "count", {"code_prefix": "A00"}
        )
        by_site = {r["site_id"]: r["value"] for r in results}
        assert by_site["clinic-01"] == 1
        assert by_site["clinic-02"] == 1


class TestFhirGitMeta:
    def test_name(self, fhir_adapter):
        assert fhir_adapter.name() == "fhir-git"

    def test_supports_aggregate(self, fhir_adapter):
        assert fhir_adapter.supports("aggregate") is True

    def test_supports_subscribe(self, fhir_adapter):
        assert fhir_adapter.supports("subscribe") is True

    def test_has_resource_type(self, fhir_adapter):
        assert fhir_adapter.has_resource_type("Condition") is True


class TestFhirGitSubscribe:
    async def test_subscribe_yields_sync_event(self, fhir_adapter):
        events = []
        async for event in fhir_adapter.subscribe(["sync.completed"]):
            events.append(event)
            if len(events) >= 1:
                break
        assert events[0].event_type == "sync.completed"
        assert events[0].resource_type == "Bundle"
