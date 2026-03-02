"""FHIR Git adapter: reads FHIR JSON from a Git repo with a SQLite index."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import aiosqlite

from open_sentinel.interfaces import DataAdapter
from open_sentinel.time_utils import parse_time_window
from open_sentinel.types import DataEvent

_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS fhir_index (
    file_path TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    code TEXT,
    site_id TEXT,
    date TEXT
);
CREATE INDEX IF NOT EXISTS idx_fhir_rt ON fhir_index(resource_type);
CREATE INDEX IF NOT EXISTS idx_fhir_code ON fhir_index(code);
CREATE INDEX IF NOT EXISTS idx_fhir_site ON fhir_index(site_id);
"""


class FhirGitAdapter(DataAdapter):
    def __init__(self, repo_path: str, index_db: str):
        self._repo_path = Path(repo_path)
        self._index_db_path = index_db
        self._db: Optional[aiosqlite.Connection] = None

    def name(self) -> str:
        return "fhir-git"

    def supports(self, feature: str) -> bool:
        return feature in ("aggregate", "subscribe")

    def has_resource_type(self, resource_type: str) -> bool:
        # Delegate to index — always return True; actual check done at query time
        return True

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._index_db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_INDEX_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def index_resource(
        self,
        file_path: str,
        resource_type: str,
        code: Optional[str] = None,
        site_id: Optional[str] = None,
        date: Optional[str] = None,
    ) -> None:
        """Add or update a resource in the index."""
        assert self._db is not None, "Call initialize() first"
        await self._db.execute(
            "INSERT OR REPLACE INTO fhir_index (file_path, resource_type, code, site_id, date) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_path, resource_type, code, site_id, date),
        )
        await self._db.commit()

    def _load_resource(self, file_path: str) -> Dict[str, Any]:
        """Read a FHIR JSON file from the repo."""
        full_path = self._repo_path / file_path
        with open(full_path) as f:
            return json.load(f)

    def _build_where(
        self, resource_type: str, filters: Dict[str, Any]
    ) -> tuple[str, List[Any]]:
        clauses = ["resource_type = ?"]
        params: List[Any] = [resource_type]

        for key, value in filters.items():
            if key == "time_window":
                td = parse_time_window(value)
                cutoff = datetime.now(timezone.utc) - td
                clauses.append("date >= ?")
                params.append(cutoff.isoformat())
            elif key.endswith("_prefix"):
                col = key[: -len("_prefix")]
                clauses.append(f"{col} LIKE ?")
                params.append(f"{value}%")
            elif isinstance(value, list):
                placeholders = ", ".join("?" for _ in value)
                clauses.append(f"{key} IN ({placeholders})")
                params.extend(value)
            else:
                clauses.append(f"{key} = ?")
                params.append(value)

        return " AND ".join(clauses), params

    async def query(
        self,
        resource_type: str,
        filters: Dict[str, Any],
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        assert self._db is not None, "Call initialize() first"
        where, params = self._build_where(resource_type, filters)
        sql = f"SELECT file_path FROM fhir_index WHERE {where}"
        if limit is not None:
            sql += f" LIMIT {limit}"
        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            resource = await asyncio.to_thread(self._load_resource, row["file_path"])
            results.append(resource)
        return results

    async def count(self, resource_type: str, filters: Dict[str, Any]) -> int:
        assert self._db is not None, "Call initialize() first"
        where, params = self._build_where(resource_type, filters)
        sql = f"SELECT COUNT(*) FROM fhir_index WHERE {where}"
        cursor = await self._db.execute(sql, params)
        row = await cursor.fetchone()
        return row[0]

    async def aggregate(
        self,
        resource_type: str,
        group_by: List[str],
        metric: str,
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        assert self._db is not None, "Call initialize() first"
        where, params = self._build_where(resource_type, filters)
        group_cols = ", ".join(group_by)

        if metric == "count":
            agg_expr = "COUNT(*)"
        elif metric == "sum":
            agg_expr = "SUM(CAST(code AS REAL))"
        elif metric == "avg":
            agg_expr = "AVG(CAST(code AS REAL))"
        else:
            raise ValueError(f"Unsupported metric: {metric}")

        sql = (
            f"SELECT {group_cols}, {agg_expr} AS value "
            f"FROM fhir_index WHERE {where} GROUP BY {group_cols}"
        )
        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def subscribe(self, event_types: List[str]) -> AsyncIterator[DataEvent]:
        yield DataEvent(
            event_type="sync.completed",
            resource_type="Bundle",
        )
        await asyncio.sleep(float("inf"))
        yield  # type: ignore[misc]
