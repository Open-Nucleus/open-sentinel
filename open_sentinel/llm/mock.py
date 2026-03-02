"""Mock LLM engine for testing."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from open_sentinel.interfaces import LLMEngine
from open_sentinel.types import (
    Alert,
    InvestigationPlan,
    InvestigationStep,
    LLMResponse,
)


class MockLLMEngine(LLMEngine):
    def __init__(
        self,
        responses: Optional[List[Dict[str, Any]]] = None,
        is_available: bool = True,
        model_name: str = "mock-model",
    ):
        self._responses = list(responses or [])
        self._call_index = 0
        self._is_available = is_available
        self._model_name = model_name
        self.call_history: List[Dict[str, Any]] = []

    def name(self) -> str:
        return "mock"

    def model(self) -> str:
        return self._model_name

    def _next_response(self) -> Dict[str, Any]:
        if not self._responses:
            return {"findings": []}
        idx = min(self._call_index, len(self._responses) - 1)
        self._call_index += 1
        return self._responses[idx]

    def _make_llm_response(self, response_data: Dict[str, Any]) -> LLMResponse:
        if isinstance(response_data, str):
            return LLMResponse(
                text=response_data,
                model=self._model_name,
                tokens_used=10,
                duration_ms=50,
            )
        text = json.dumps(response_data)
        return LLMResponse(
            text=text,
            structured=response_data,
            model=self._model_name,
            confidence=response_data.get("confidence"),
            tokens_used=response_data.get("tokens_used", 10),
            duration_ms=response_data.get("duration_ms", 50),
        )

    async def reason(
        self,
        system_prompt: str,
        clinical_context: str,
        question: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        self.call_history.append({
            "method": "reason",
            "system_prompt": system_prompt,
            "clinical_context": clinical_context,
            "question": question,
            "schema": schema,
        })
        return self._make_llm_response(self._next_response())

    async def reflect(
        self,
        original_findings: List[Dict[str, Any]],
        critique: str,
        clinical_context: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        self.call_history.append({
            "method": "reflect",
            "original_findings": original_findings,
            "critique": critique,
            "clinical_context": clinical_context,
            "schema": schema,
        })
        return self._make_llm_response(self._next_response())

    async def explain(self, alert: Alert, context: str) -> str:
        self.call_history.append({
            "method": "explain",
            "alert_id": alert.id,
            "context": context,
        })
        return f"Explanation for alert {alert.title}"

    async def plan(
        self,
        goal: str,
        available_data: List[str],
        constraints: Dict[str, Any],
    ) -> InvestigationPlan:
        self.call_history.append({
            "method": "plan",
            "goal": goal,
            "available_data": available_data,
            "constraints": constraints,
        })
        return InvestigationPlan(
            goal=goal,
            steps=[
                InvestigationStep(
                    description="Mock step",
                    analysis_question="Mock question",
                )
            ],
            rationale="Mock plan",
        )

    async def available(self) -> bool:
        return self._is_available

    def set_available(self, value: bool) -> None:
        self._is_available = value
