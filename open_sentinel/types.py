"""Core types for open-sentinel. All Pydantic v2 models."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Priority(enum.IntEnum):
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1


class SkillTrigger(str, enum.Enum):
    EVENT = "event"
    SCHEDULE = "schedule"
    BOTH = "both"
    MANUAL = "manual"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


class DataEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: str
    resource_type: str
    resource_id: Optional[str] = None
    resource_data: Optional[Dict[str, Any]] = None
    site_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: Optional[Dict[str, Any]] = None


class DataRequirement(BaseModel):
    resource_type: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    time_window: Optional[str] = None
    group_by: Optional[List[str]] = None
    metric: Optional[str] = None
    limit: Optional[int] = None
    name: Optional[str] = None


class LLMResponse(BaseModel):
    text: str
    structured: Optional[Dict[str, Any]] = None
    model: str
    confidence: Optional[float] = None
    tokens_used: int = 0
    duration_ms: int = 0


class Alert(BaseModel):
    # Identity
    id: str = Field(default_factory=_uuid)
    skill_name: str = ""
    severity: str = "moderate"
    category: str = ""
    title: str = ""
    description: str = ""

    # Context
    patient_id: Optional[str] = None
    patient_ids: Optional[List[str]] = None
    site_id: Optional[str] = None
    site_ids: Optional[List[str]] = None

    # Evidence
    evidence: Optional[Dict[str, Any]] = None
    threshold: Optional[str] = None
    measured_value: Optional[float] = None
    threshold_value: Optional[float] = None

    # LLM provenance
    ai_generated: bool = False
    ai_confidence: Optional[float] = None
    ai_model: Optional[str] = None
    ai_reasoning: Optional[str] = None
    rule_validated: bool = False
    reflection_iterations: int = 0
    requires_review: bool = True

    # Outcome
    outcome: str = "pending"
    clinician_feedback: Optional[str] = None

    # Deduplication
    dedup_key: Optional[str] = None

    # FHIR mapping
    fhir_resource_type: str = "DetectedIssue"
    fhir_code: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=_utcnow)
    reviewed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _enforce_requires_review(self) -> "Alert":
        object.__setattr__(self, "requires_review", True)
        return self


class Episode(BaseModel):
    id: str = Field(default_factory=_uuid)
    skill_name: str = ""
    site_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)
    trigger: str = ""
    findings_summary: str = ""
    alerts_generated: int = 0
    outcome: str = "pending"
    clinician_feedback: Optional[str] = None
    data_snapshot: Optional[Dict[str, Any]] = None
    related_alert_ids: Optional[List[str]] = None


class InvestigationStep(BaseModel):
    description: str
    data_needed: Optional[DataRequirement] = None
    analysis_question: str
    depends_on: Optional[str] = None


class InvestigationPlan(BaseModel):
    goal: str
    steps: List[InvestigationStep]
    estimated_data_requirements: List[DataRequirement] = Field(default_factory=list)
    rationale: str = ""


class AgentConfig(BaseModel):
    hardware: str = "pi4_8gb"
    state_db_path: str = "sentinel_state.db"
    skill_config: Dict[str, Any] = Field(default_factory=dict)
    max_critical_per_hour: int = 10
    llm_timeout_seconds: int = 60


class AnalysisContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    trigger: str
    trigger_event: Optional[DataEvent] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    site_id: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    llm: Any = None
    memory: Any = None
    episodes: List[Episode] = Field(default_factory=list)
    baselines: Dict[str, float] = Field(default_factory=dict)
    previous_alerts: List[Alert] = Field(default_factory=list)
