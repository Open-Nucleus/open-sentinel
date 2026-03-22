"""OpenAIEngine — uses the official openai Python SDK for cloud LLM access.

Cloud LLMs never see patient identifiers. Only aggregated/anonymised data
should be sent via skill prompts.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from open_sentinel.interfaces import LLMEngine
from open_sentinel.types import (
    Alert,
    InvestigationPlan,
    InvestigationStep,
    LLMResponse,
)

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


class OpenAIEngine(LLMEngine):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o",
        timeout: float = 60.0,
        base_url: Optional[str] = None,
    ):
        if openai is None:
            raise ImportError(
                "The openai package is required. Install it with: "
                "pip install open-sentinel[openai]"
            )
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OpenAI API key required. Pass api_key= or set OPENAI_API_KEY env var."
            )
        self._model_name = model_name
        self._client = openai.AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url,
            timeout=timeout,
        )

    def name(self) -> str:
        return "openai"

    def model(self) -> str:
        return self._model_name

    async def _chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        kwargs: Dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0.1,
        }
        if schema:
            kwargs["response_format"] = {"type": "json_object"}

        start = time.monotonic()
        response = await self._client.chat.completions.create(**kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)

        text = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0

        structured = None
        confidence = None
        if schema:
            try:
                structured = json.loads(text)
                confidence = structured.get("confidence")
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON response from OpenAI")

        return LLMResponse(
            text=text,
            structured=structured,
            model=self._model_name,
            confidence=confidence,
            tokens_used=tokens,
            duration_ms=duration_ms,
        )

    async def reason(
        self,
        system_prompt: str,
        clinical_context: str,
        question: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{clinical_context}\n\n{question}"},
        ]
        if schema:
            schema_inst = (
                "\n\nRespond with JSON matching this schema:\n"
                + json.dumps(schema)
            )
            messages[0]["content"] += schema_inst
        return await self._chat(messages, schema)

    async def reflect(
        self,
        original_findings: List[Dict[str, Any]],
        critique: str,
        clinical_context: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        sys_content = (
            "You are a clinical surveillance analyst. "
            "Revise your findings based on the critique provided."
        )
        messages = [
            {"role": "system", "content": sys_content},
            {
                "role": "user",
                "content": (
                    f"Original findings:\n{json.dumps(original_findings)}\n\n"
                    f"Critique:\n{critique}\n\n"
                    f"Clinical context:\n{clinical_context}\n\n"
                    "Please revise your findings to address the critique."
                ),
            },
        ]
        if schema:
            schema_inst = (
                "\n\nRespond with JSON matching this schema:\n"
                + json.dumps(schema)
            )
            messages[0]["content"] += schema_inst
        return await self._chat(messages, schema)

    async def explain(self, alert: Alert, context: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Provide a clear, concise explanation of this "
                    "clinical alert for a healthcare worker."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Alert: {alert.title}\n"
                    f"Severity: {alert.severity}\n"
                    f"Description: {alert.description}\n\n"
                    f"Context: {context}"
                ),
            },
        ]
        response = await self._chat(messages)
        return response.text

    async def plan(
        self,
        goal: str,
        available_data: List[str],
        constraints: Dict[str, Any],
    ) -> InvestigationPlan:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a clinical surveillance analyst. Create an investigation plan. "
                    'Respond with JSON: {"goal": str, "steps": [{"description": str, '
                    '"analysis_question": str}], "rationale": str}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Goal: {goal}\n"
                    f"Available data: {', '.join(available_data)}\n"
                    f"Constraints: {json.dumps(constraints)}"
                ),
            },
        ]
        response = await self._chat(messages, schema={"type": "object"})
        if response.structured:
            steps = [
                InvestigationStep(
                    description=s.get("description", ""),
                    analysis_question=s.get("analysis_question", ""),
                )
                for s in response.structured.get("steps", [])
            ]
            return InvestigationPlan(
                goal=response.structured.get("goal", goal),
                steps=steps,
                rationale=response.structured.get("rationale", ""),
            )
        return InvestigationPlan(goal=goal, steps=[], rationale=response.text)

    async def available(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
