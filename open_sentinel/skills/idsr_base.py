"""IdsrBaseSkill: shared base class for all WHO IDSR epidemic skills."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from open_sentinel.interfaces import Skill
from open_sentinel.time_utils import epiweek
from open_sentinel.types import AnalysisContext, Priority, SkillTrigger

_SEVERITY_ORDER = {"low": 1, "moderate": 2, "high": 3, "critical": 4}

IDSR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["low", "moderate", "high", "critical"],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "site_id": {"type": "string"},
                    "measured_value": {"type": "number"},
                    "threshold_value": {"type": "number"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "object"},
                    "dedup_key": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["severity", "title", "site_id", "measured_value", "confidence"],
            },
        }
    },
    "required": ["findings"],
}


class IdsrBaseSkill(Skill):
    """Base class for IDSR epidemic surveillance skills."""

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.BOTH

    def priority(self) -> Priority:
        return Priority.CRITICAL

    def max_reflections(self) -> int:
        return 2

    def response_schema(self) -> Optional[Dict[str, Any]]:
        return IDSR_RESPONSE_SCHEMA

    def _dedup_key(self, site_id: str, dt) -> str:
        return f"{self.name()}-{site_id}-{epiweek(dt)}"

    @staticmethod
    def _site_counts(ctx: AnalysisContext, data_key: str) -> Dict[str, int]:
        """Extract {site_id: count} from aggregate data in ctx.data."""
        data = ctx.data.get(data_key, [])
        result: Dict[str, int] = {}
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    site = row.get("site_id", "unknown")
                    result[site] = result.get(site, 0) + int(row.get("value", row.get("count", 1)))
        return result

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        """Cross-reference claimed measured_value against actual data."""
        issues = []
        for finding in findings:
            site_id = finding.get("site_id")
            claimed = finding.get("measured_value")
            if site_id is None or claimed is None:
                continue

            # Check against all data keys for a match
            found_match = False
            for data_key, data_values in ctx.data.items():
                if isinstance(data_values, list):
                    for row in data_values:
                        if isinstance(row, dict) and row.get("site_id") == site_id:
                            actual = row.get("value", row.get("count"))
                            if actual is not None:
                                actual = float(actual)
                                if abs(float(claimed) - actual) < 0.01:
                                    found_match = True
                                    break
                                elif float(claimed) > actual * 2:
                                    issues.append(
                                        f"Finding claims {claimed} for "
                                        f"{site_id} but data shows {actual}"
                                    )
                                    found_match = True
                                    break
                    if found_match:
                        break

        if issues:
            return "REVISE: " + "; ".join(issues)
        return "ACCEPT"
