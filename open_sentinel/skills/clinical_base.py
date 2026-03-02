"""Shared schemas and helpers for clinical/supply skills (not a base class)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from open_sentinel.time_utils import epiweek
from open_sentinel.types import AnalysisContext

CLINICAL_RESPONSE_SCHEMA = {
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
                    "patient_id": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "object"},
                    "dedup_key": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["severity", "title", "patient_id", "confidence"],
            },
        }
    },
    "required": ["findings"],
}

SUPPLY_RESPONSE_SCHEMA = {
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
                    "confidence": {"type": "number"},
                    "item_code": {"type": "string"},
                    "days_remaining": {"type": "number"},
                    "evidence": {"type": "object"},
                    "dedup_key": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["severity", "title", "site_id", "confidence"],
            },
        }
    },
    "required": ["findings"],
}


def patient_dedup_key(skill_name: str, patient_id: str, dt: datetime) -> str:
    return f"{skill_name}-{patient_id}-{dt.strftime('%Y-%m-%d')}"


def site_dedup_key(skill_name: str, site_id: str, dt: datetime) -> str:
    return f"{skill_name}-{site_id}-{epiweek(dt)}"


def extract_records(ctx: AnalysisContext, data_key: str) -> List[Dict[str, Any]]:
    data = ctx.data.get(data_key, [])
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def critique_patient_findings(
    findings: List[Dict[str, Any]],
    ctx: AnalysisContext,
    data_key: str,
) -> str:
    """Validate that patient IDs in findings exist in the actual data."""
    records = extract_records(ctx, data_key)
    known_patients = set()
    for r in records:
        pid = r.get("patient_id") or r.get("id") or r.get("subject", {}).get("reference", "")
        if pid:
            known_patients.add(pid)

    issues = []
    for finding in findings:
        pid = finding.get("patient_id")
        if pid and known_patients and pid not in known_patients:
            issues.append(f"patient {pid} not in data")

    if issues:
        return "REVISE: " + "; ".join(issues)
    return "ACCEPT"
