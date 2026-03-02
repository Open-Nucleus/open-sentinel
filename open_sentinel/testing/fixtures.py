"""Test fixture factories for data events, alerts, and episodes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from open_sentinel.types import Alert, DataEvent, Episode


def make_data_event(
    event_type: str = "resource.created",
    resource_type: str = "Condition",
    resource_id: Optional[str] = None,
    resource_data: Optional[Dict[str, Any]] = None,
    site_id: Optional[str] = "site-1",
    **kwargs: Any,
) -> DataEvent:
    return DataEvent(
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_data=resource_data,
        site_id=site_id,
        **kwargs,
    )


def make_alert(
    skill_name: str = "test-skill",
    severity: str = "moderate",
    title: str = "Test Alert",
    ai_generated: bool = True,
    ai_confidence: float = 0.85,
    site_id: Optional[str] = "site-1",
    **kwargs: Any,
) -> Alert:
    return Alert(
        skill_name=skill_name,
        severity=severity,
        title=title,
        ai_generated=ai_generated,
        ai_confidence=ai_confidence,
        site_id=site_id,
        **kwargs,
    )


def make_episode(
    skill_name: str = "test-skill",
    site_id: str = "site-1",
    findings_summary: str = "Test findings",
    alerts_generated: int = 1,
    outcome: str = "pending",
    **kwargs: Any,
) -> Episode:
    return Episode(
        skill_name=skill_name,
        site_id=site_id,
        findings_summary=findings_summary,
        alerts_generated=alerts_generated,
        outcome=outcome,
        **kwargs,
    )
