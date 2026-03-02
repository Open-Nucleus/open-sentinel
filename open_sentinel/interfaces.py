"""Five core ABCs defining the plugin contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from open_sentinel.types import (
    Alert,
    AnalysisContext,
    DataEvent,
    DataRequirement,
    Episode,
    InvestigationPlan,
    LLMResponse,
    Priority,
    SkillTrigger,
)


class DataAdapter(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def query(
        self,
        resource_type: str,
        filters: Dict[str, Any],
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def count(self, resource_type: str, filters: Dict[str, Any]) -> int: ...

    @abstractmethod
    async def subscribe(self, event_types: List[str]) -> AsyncIterator[DataEvent]: ...

    @abstractmethod
    async def aggregate(
        self,
        resource_type: str,
        group_by: List[str],
        metric: str,
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]: ...

    def supports(self, feature: str) -> bool:
        return False

    def has_resource_type(self, resource_type: str) -> bool:
        return True


class LLMEngine(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    async def reason(
        self,
        system_prompt: str,
        clinical_context: str,
        question: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def reflect(
        self,
        original_findings: List[Dict[str, Any]],
        critique: str,
        clinical_context: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def explain(self, alert: Alert, context: str) -> str: ...

    @abstractmethod
    async def plan(
        self,
        goal: str,
        available_data: List[str],
        constraints: Dict[str, Any],
    ) -> InvestigationPlan: ...

    @abstractmethod
    async def available(self) -> bool: ...


class Skill(ABC):
    @abstractmethod
    def name(self) -> str: ...

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.EVENT

    def schedule(self) -> Optional[str]:
        return None

    def event_filter(self) -> Optional[Dict[str, Any]]:
        return None

    def priority(self) -> Priority:
        return Priority.MEDIUM

    @abstractmethod
    def required_data(self) -> Dict[str, DataRequirement]: ...

    @abstractmethod
    def build_prompt(self, ctx: AnalysisContext) -> str: ...

    def response_schema(self) -> Optional[Dict[str, Any]]:
        return None

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        return "ACCEPT"

    def max_reflections(self) -> int:
        return 2

    @abstractmethod
    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]: ...

    def goal(self) -> str:
        return ""

    def success_criteria(self) -> Dict[str, Any]:
        return {}

    def can_request_additional_data(self) -> bool:
        return False

    def handle_additional_data_request(self, request: Dict[str, Any]) -> DataRequirement:
        raise NotImplementedError


class AlertOutput(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def emit(self, alert: Alert) -> bool: ...

    @abstractmethod
    def accepts(self, alert: Alert) -> bool: ...


class MemoryStore(ABC):
    # Working memory
    @abstractmethod
    async def get_working(self, key: str) -> Any: ...

    @abstractmethod
    async def set_working(self, key: str, value: Any) -> None: ...

    @abstractmethod
    async def clear_working(self) -> None: ...

    # Episodic memory
    @abstractmethod
    async def store_episode(self, episode: Episode) -> None: ...

    @abstractmethod
    async def recall_episodes(
        self, skill_name: str, site_id: str, limit: int = 5
    ) -> List[Episode]: ...

    @abstractmethod
    async def update_episode_outcome(
        self, alert_id: str, outcome: str, feedback: Optional[str] = None
    ) -> None: ...

    # Semantic memory
    @abstractmethod
    async def get_baseline(
        self, skill_name: str, site_id: str, metric: str
    ) -> Optional[float]: ...

    @abstractmethod
    async def update_baseline(
        self, skill_name: str, site_id: str, metric: str, value: float
    ) -> None: ...

    # Procedural memory
    @abstractmethod
    async def get_skill_state(self, skill_name: str, key: str) -> Any: ...

    @abstractmethod
    async def set_skill_state(self, skill_name: str, key: str, value: Any) -> None: ...

    # Alert history
    @abstractmethod
    async def store_alert(self, alert: Alert) -> None: ...

    @abstractmethod
    async def get_alert(self, alert_id: str) -> Optional[Alert]: ...

    @abstractmethod
    async def recent_alerts(
        self, skill_name: str, limit: int = 20
    ) -> List[Alert]: ...

    @abstractmethod
    async def update_alert_outcome(
        self, alert_id: str, outcome: str, feedback: Optional[str] = None
    ) -> None: ...

    @abstractmethod
    async def count_recent_alerts(
        self, skill_name: str, severity: Optional[str] = None, window_hours: int = 1
    ) -> int: ...

    # Emission queue
    @abstractmethod
    async def queue_emission(
        self, alert_id: str, output_name: str, data: str
    ) -> None: ...

    @abstractmethod
    async def get_pending_emissions(self, limit: int = 50) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def mark_emission_complete(self, emission_id: str) -> None: ...

    @abstractmethod
    async def mark_emission_failed(
        self, emission_id: str, next_retry: datetime
    ) -> None: ...
