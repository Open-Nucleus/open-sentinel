"""OllamaEngine — uses OpenAI-compatible /v1/chat/completions endpoint.

Works with Ollama, llama.cpp, vLLM, LocalAI, or any medical fine-tuned model
exposing the OpenAI-compatible API.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from open_sentinel.interfaces import LLMEngine
from open_sentinel.types import (
    Alert,
    InvestigationPlan,
    InvestigationStep,
    LLMResponse,
)

logger = logging.getLogger(__name__)


class OllamaEngine(LLMEngine):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "phi3:mini",
        timeout: float = 60.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    def name(self) -> str:
        return "ollama"

    def model(self) -> str:
        return self._model_name

    async def _chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        url = f"{self._base_url}/v1/chat/completions"

        body: Dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0.1,
        }
        if schema:
            body["response_format"] = {"type": "json_object"}

        start = time.monotonic()
        response = await self._client.post(url, json=body)
        response.raise_for_status()
        duration_ms = int((time.monotonic() - start) * 1000)

        data = response.json()
        choice = data["choices"][0]
        text = choice["message"]["content"]
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)

        structured = None
        confidence = None
        if schema:
            try:
                structured = json.loads(text)
                confidence = structured.get("confidence")
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON response from LLM")

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
        sys_content = (
            "Provide a clear, concise explanation of this "
            "clinical alert for a healthcare worker."
        )
        messages = [
            {"role": "system", "content": sys_content},
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
                    "Respond with JSON: {\"goal\": str, \"steps\": [{\"description\": str, "
                    "\"analysis_question\": str}], \"rationale\": str}"
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
            response = await self._client.get(
                f"{self._base_url}/v1/models", timeout=5.0
            )
            return response.status_code == 200
        except (httpx.HTTPError, Exception):
            return False
