"""Tests for HookRegistry."""

import pytest

from open_sentinel.hooks import VALID_HOOKS, HookRegistry


class TestHookRegistry:
    async def test_register_and_run(self):
        registry = HookRegistry()
        calls = []

        async def handler(*args):
            calls.append(args)

        registry.register("before_skill_run", handler)
        await registry.run("before_skill_run", "skill1", "ctx")
        assert len(calls) == 1
        assert calls[0] == ("skill1", "ctx")

    async def test_invalid_hook_raises(self):
        registry = HookRegistry()

        async def handler():
            pass

        with pytest.raises(ValueError, match="Invalid hook name"):
            registry.register("not_a_real_hook", handler)

    async def test_all_valid_hooks(self):
        expected = {
            "before_data_fetch", "after_data_fetch",
            "before_skill_run", "after_skill_run",
            "before_alert_emit", "after_alert_emit",
            "before_llm_prompt", "after_llm_response",
            "on_reflection", "on_degraded_mode", "on_feedback",
        }
        assert VALID_HOOKS == expected

    async def test_handler_exception_ignored(self):
        registry = HookRegistry()
        calls = []

        async def bad_handler(*args):
            raise RuntimeError("boom")

        async def good_handler(*args):
            calls.append(args)

        registry.register("on_feedback", bad_handler)
        registry.register("on_feedback", good_handler)
        await registry.run("on_feedback", "alert-1", "confirmed")
        assert len(calls) == 1

    async def test_no_handlers_runs_fine(self):
        registry = HookRegistry()
        await registry.run("before_skill_run", "x")

    async def test_multiple_hooks(self):
        registry = HookRegistry()
        calls = []

        async def h1(*args):
            calls.append("h1")

        async def h2(*args):
            calls.append("h2")

        registry.register("before_alert_emit", h1)
        registry.register("before_alert_emit", h2)
        await registry.run("before_alert_emit")
        assert calls == ["h1", "h2"]
