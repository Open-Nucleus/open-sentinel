"""CSV/TSV data adapter: reads clinical data from CSV files in a directory."""

from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from open_sentinel.interfaces import DataAdapter
from open_sentinel.time_utils import parse_time_window
from open_sentinel.types import DataEvent


class CsvAdapter(DataAdapter):
    def __init__(
        self,
        directory: str,
        resource_type_file_map: Dict[str, str],
        delimiter: str = ",",
        time_column: str = "date",
    ):
        self._directory = Path(directory)
        self._resource_type_file_map = resource_type_file_map
        self._delimiter = delimiter
        self._time_column = time_column

    def name(self) -> str:
        return "csv"

    def supports(self, feature: str) -> bool:
        return feature == "aggregate"

    def has_resource_type(self, resource_type: str) -> bool:
        return resource_type in self._resource_type_file_map

    def _load_csv(self, resource_type: str) -> List[Dict[str, Any]]:
        filename = self._resource_type_file_map.get(resource_type)
        if not filename:
            return []
        filepath = self._directory / filename
        if not filepath.exists():
            return []
        with open(filepath, newline="") as f:
            reader = csv.DictReader(f, delimiter=self._delimiter)
            return list(reader)

    def _filter_rows(
        self,
        rows: List[Dict[str, Any]],
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        result = rows
        time_window = filters.get("time_window")
        if time_window:
            cutoff = datetime.now(timezone.utc) - parse_time_window(time_window)
            cutoff_str = cutoff.isoformat()
            filtered = []
            for row in result:
                date_val = row.get(self._time_column, "")
                if date_val >= cutoff_str:
                    filtered.append(row)
            result = filtered

        for key, value in filters.items():
            if key == "time_window":
                continue
            if isinstance(value, list):
                result = [r for r in result if r.get(key) in value]
            elif key.endswith("_prefix"):
                col = key[: -len("_prefix")]
                result = [r for r in result if r.get(col, "").startswith(value)]
            else:
                result = [r for r in result if r.get(key) == value]
        return result

    async def query(
        self,
        resource_type: str,
        filters: Dict[str, Any],
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        rows = await asyncio.to_thread(self._load_csv, resource_type)
        rows = self._filter_rows(rows, filters)
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def count(self, resource_type: str, filters: Dict[str, Any]) -> int:
        rows = await self.query(resource_type, filters)
        return len(rows)

    async def aggregate(
        self,
        resource_type: str,
        group_by: List[str],
        metric: str,
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        rows = await asyncio.to_thread(self._load_csv, resource_type)
        rows = self._filter_rows(rows, filters)

        groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for row in rows:
            key = tuple(row.get(col, "") for col in group_by)
            groups.setdefault(key, []).append(row)

        results = []
        for key, group_rows in groups.items():
            entry: Dict[str, Any] = {}
            for i, col in enumerate(group_by):
                entry[col] = key[i]
            if metric == "count":
                entry["value"] = len(group_rows)
            elif metric == "sum":
                entry["value"] = sum(float(r.get("value", 0)) for r in group_rows)
            elif metric == "avg":
                vals = [float(r.get("value", 0)) for r in group_rows]
                entry["value"] = sum(vals) / len(vals) if vals else 0
            results.append(entry)
        return results

    async def subscribe(self, event_types: List[str]) -> AsyncIterator[DataEvent]:
        for resource_type in self._resource_type_file_map:
            yield DataEvent(
                event_type="sync.completed",
                resource_type=resource_type,
            )
        await asyncio.sleep(float("inf"))
        yield  # type: ignore[misc]  # unreachable, satisfies generator protocol
