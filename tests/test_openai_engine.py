"""Tests for OpenAIEngine — all API calls are mocked."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

openai = pytest.importorskip("openai")

from open_sentinel.llm.openai_engine import OpenAIEngine
from open_sentinel.testing.fixtures import make_alert
from open_sentinel.types import InvestigationPlan, LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_completion(content: str = "", total_tokens: int = 100) -> MagicMock:
    """Build a mock that looks like an OpenAI ChatCompletion response."""
    mock = MagicMock()
    mock.choices = [MagicMock(message=MagicMock(content=content))]
    mock.usage = MagicMock(total_tokens=total_tokens)
    return mock


def _make_engine(model: str = "gpt-4o") -> OpenAIEngine:
    """Create an OpenAIEngine with a fake key and mock client."""
    engine = OpenAIEngine(api_key="test-key", model_name=model)
    engine._client = MagicMock()
    return engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNameAndModel:
    def test_name_returns_openai(self):
        engine = _make_engine()
        assert engine.name() == "openai"

    def test_model_returns_configured_model(self):
        engine = _make_engine("gpt-4o-mini")
        assert engine.model() == "gpt-4o-mini"

    def test_model_default(self):
        engine = _make_engine()
        assert engine.model() == "gpt-4o"


class TestReason:
    async def test_reason_message_format(self):
        engine = _make_engine()
        schema = {"type": "object", "properties": {"confidence": {"type": "number"}}}
        response_json = json.dumps({"confidence": 0.85, "findings": []})

        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content=response_json, total_tokens=42)
        )

        result = await engine.reason(
            system_prompt="You are an analyst.",
            clinical_context="5 cholera cases in Kambia",
            question="Is this an outbreak?",
            schema=schema,
        )

        call_kwargs = engine._client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]

        # System message should contain original prompt + schema instructions
        assert messages[0]["role"] == "system"
        assert "You are an analyst." in messages[0]["content"]
        assert "Respond with JSON matching this schema" in messages[0]["content"]
        assert json.dumps(schema) in messages[0]["content"]

        # User message should combine clinical_context and question
        assert messages[1]["role"] == "user"
        assert "5 cholera cases in Kambia" in messages[1]["content"]
        assert "Is this an outbreak?" in messages[1]["content"]

        # response_format should be set when schema is provided
        assert call_kwargs["response_format"] == {"type": "json_object"}

        assert isinstance(result, LLMResponse)

    async def test_reason_without_schema(self):
        engine = _make_engine()
        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content="No outbreak detected.")
        )

        await engine.reason(
            system_prompt="You are an analyst.",
            clinical_context="context",
            question="question",
            schema=None,
        )

        call_kwargs = engine._client.chat.completions.create.call_args.kwargs

        # No response_format when schema is None
        assert "response_format" not in call_kwargs

        # System message should NOT contain schema instructions
        assert "Respond with JSON" not in call_kwargs["messages"][0]["content"]


class TestReflect:
    async def test_reflect_message_format(self):
        engine = _make_engine()
        response_json = json.dumps({"findings": [{"title": "Revised"}]})
        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content=response_json)
        )

        original_findings = [{"severity": "critical", "title": "Original"}]
        critique = "Finding lacks supporting evidence"
        clinical_context = "5 cholera cases"

        await engine.reflect(
            original_findings=original_findings,
            critique=critique,
            clinical_context=clinical_context,
            schema={"type": "object"},
        )

        call_kwargs = engine._client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]

        # System message should mention revision
        assert messages[0]["role"] == "system"
        assert "Revise" in messages[0]["content"] or "revise" in messages[0]["content"].lower()

        # User message should contain all three pieces
        user_content = messages[1]["content"]
        assert json.dumps(original_findings) in user_content
        assert critique in user_content
        assert clinical_context in user_content


class TestExplain:
    async def test_explain_returns_text(self):
        engine = _make_engine()
        explanation = "This alert indicates a potential cholera outbreak."
        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content=explanation)
        )

        alert = make_alert(title="Cholera outbreak", severity="critical")
        result = await engine.explain(alert, context="Kambia district")

        assert result == explanation
        assert isinstance(result, str)


class TestPlan:
    async def test_plan_returns_investigation_plan(self):
        engine = _make_engine()
        plan_json = json.dumps({
            "goal": "Investigate cholera cluster",
            "steps": [
                {
                    "description": "Collect water samples",
                    "analysis_question": "Is the water source contaminated?",
                },
                {
                    "description": "Map case locations",
                    "analysis_question": "Is there geographic clustering?",
                },
            ],
            "rationale": "Standard cholera investigation protocol",
        })
        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content=plan_json)
        )

        result = await engine.plan(
            goal="Investigate cholera cluster",
            available_data=["case_reports", "water_quality"],
            constraints={"max_steps": 5},
        )

        assert isinstance(result, InvestigationPlan)
        assert result.goal == "Investigate cholera cluster"
        assert len(result.steps) == 2
        assert result.steps[0].description == "Collect water samples"
        assert result.steps[1].analysis_question == "Is there geographic clustering?"
        assert result.rationale == "Standard cholera investigation protocol"

    async def test_plan_fallback_on_bad_json(self):
        engine = _make_engine()
        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content="This is not valid JSON at all")
        )

        result = await engine.plan(
            goal="Investigate outbreak",
            available_data=["case_reports"],
            constraints={},
        )

        assert isinstance(result, InvestigationPlan)
        # Fallback: goal passed through, no steps, rationale is raw text
        assert result.goal == "Investigate outbreak"
        assert result.steps == []
        assert "This is not valid JSON at all" in result.rationale


class TestJsonParsing:
    async def test_json_parsing_and_confidence(self):
        engine = _make_engine()
        response_json = json.dumps({
            "confidence": 0.92,
            "findings": [{"title": "Outbreak detected"}],
        })
        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content=response_json, total_tokens=75)
        )

        result = await engine.reason(
            system_prompt="Analyze.",
            clinical_context="context",
            question="question",
            schema={"type": "object"},
        )

        assert result.structured is not None
        assert result.structured["confidence"] == 0.92
        assert result.confidence == 0.92
        assert result.structured["findings"][0]["title"] == "Outbreak detected"

    async def test_json_parse_failure_graceful(self):
        engine = _make_engine()
        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content="not valid json {{{")
        )

        # Schema is provided but response is not valid JSON
        result = await engine.reason(
            system_prompt="Analyze.",
            clinical_context="context",
            question="question",
            schema={"type": "object"},
        )

        # Should not raise; structured should be None
        assert result.structured is None
        assert result.confidence is None
        assert result.text == "not valid json {{{"


class TestAvailable:
    async def test_available_success(self):
        engine = _make_engine()
        engine._client.models.list = AsyncMock(return_value=MagicMock())

        assert await engine.available() is True

    async def test_available_failure(self):
        engine = _make_engine()
        engine._client.models.list = AsyncMock(side_effect=Exception("connection refused"))

        assert await engine.available() is False


class TestConstructorValidation:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OpenAI API key required"):
            OpenAIEngine(api_key=None)

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-test-key")
        engine = OpenAIEngine()
        assert engine.name() == "openai"

    def test_missing_openai_package(self):
        """Verify ImportError message when openai package is missing."""
        with patch("open_sentinel.llm.openai_engine.openai", None):
            with pytest.raises(ImportError, match="openai package is required"):
                OpenAIEngine(api_key="test-key")


class TestTokensAndDuration:
    async def test_tokens_and_duration_populated(self):
        engine = _make_engine()
        engine._client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(content="result", total_tokens=256)
        )

        result = await engine.reason(
            system_prompt="Analyze.",
            clinical_context="context",
            question="question",
        )

        assert result.tokens_used == 256
        assert result.duration_ms >= 0
        assert result.model == "gpt-4o"

    async def test_tokens_zero_when_no_usage(self):
        engine = _make_engine()
        mock_resp = _mock_completion(content="result")
        mock_resp.usage = None
        engine._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        result = await engine.reason(
            system_prompt="Analyze.",
            clinical_context="context",
            question="question",
        )

        assert result.tokens_used == 0
