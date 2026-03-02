"""SQLite data adapter: reads clinical data from a user-managed SQLite database."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

import aiosqlite

from open_sentinel.interfaces import DataAdapter
from open_sentinel.time_utils import parse_time_window
from open_sentinel.types import DataEvent


class SqliteAdapter(DataAdapter):
    def __init__(
        self,
        db_path: str,
        resource_type_table_map: Dict[str, str],
        time_column: str = "recorded_date",
    ):
        self._db_path = db_path
        self._resource_type_table_map = resource_type_table_map
        self._time_column = time_column
        self._db: Optional[aiosqlite.Connection] = None

    def name(self) -> str:
        return "sqlite"

    def supports(self, feature: str) -> bool:
        return feature == "aggregate"

    def has_resource_type(self, resource_type: str) -> bool:
        return resource_type in self._resource_type_table_map

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _table_for(self, resource_type: str) -> str:
        table = self._resource_type_table_map.get(resource_type)
        if not table:
            raise ValueError(f"Unknown resource type: {resource_type}")
        return table

    def _build_where(
        self, filters: Dict[str, Any], table: str
    ) -> tuple[str, List[Any]]:
        clauses: List[str] = []
        params: List[Any] = []

        for key, value in filters.items():
            if key == "time_window":
                td = parse_time_window(value)
                cutoff = datetime.now(timezone.utc) - td
                clauses.append(f"{self._time_column} >= ?")
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

        where = " AND ".join(clauses) if clauses else "1=1"
        return where, params

    async def query(
        self,
        resource_type: str,
        filters: Dict[str, Any],
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        assert self._db is not None, "Call initialize() first"
        table = self._table_for(resource_type)
        where, params = self._build_where(filters, table)
        sql = f"SELECT * FROM {table} WHERE {where}"
        if limit is not None:
            sql += f" LIMIT {limit}"
        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def count(self, resource_type: str, filters: Dict[str, Any]) -> int:
        assert self._db is not None, "Call initialize() first"
        table = self._table_for(resource_type)
        where, params = self._build_where(filters, table)
        sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
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
        table = self._table_for(resource_type)
        where, params = self._build_where(filters, table)

        group_cols = ", ".join(group_by)
        if metric == "count":
            agg_expr = "COUNT(*)"
        elif metric == "sum":
            agg_expr = "SUM(value)"
        elif metric == "avg":
            agg_expr = "AVG(value)"
        else:
            raise ValueError(f"Unsupported metric: {metric}")

        sql = (
            f"SELECT {group_cols}, {agg_expr} AS value "
            f"FROM {table} WHERE {where} GROUP BY {group_cols}"
        )
        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def subscribe(self, event_types: List[str]) -> AsyncIterator[DataEvent]:
        for resource_type in self._resource_type_table_map:
            yield DataEvent(
                event_type="sync.completed",
                resource_type=resource_type,
            )
        await asyncio.sleep(float("inf"))
        yield  # type: ignore[misc]
