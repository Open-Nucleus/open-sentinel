#!/usr/bin/env python3
"""Open-Sentinel clinical surveillance demo using OpenAI.

Runs the IDSR cholera outbreak detection skill against sample surveillance
data from three health facilities in Lusaka, Zambia. The LLM analyzes case
counts, compares to baselines, and generates prioritized alerts with full
AI provenance tracking.

Usage:
    # Option 1: Create a .env file with OPENAI_API_KEY=sk-...
    python demo.py

    # Option 2: Pass inline
    OPENAI_API_KEY=sk-... python demo.py
    OPENAI_API_KEY=sk-... OPENAI_MODEL=gpt-4o-mini python demo.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Skill loader (same pattern as tests/test_idsr_skills.py)
# ---------------------------------------------------------------------------

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _import_skill(folder: str, module_name: str):
    """Import a skill module from a hyphenated skill directory."""
    skill_path = _SKILLS_DIR / folder / "skill.py"
    spec = importlib.util.spec_from_file_location(module_name, skill_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Sample surveillance data — simulated cholera outbreak in Lusaka district
# ---------------------------------------------------------------------------

SAMPLE_DATA = {
    "cholera_this_week": [
        {"site_id": "Kanyama-HC", "value": 5},
        {"site_id": "Chilenje-HC", "value": 0},
        {"site_id": "Matero-L1", "value": 12},
    ],
    "cholera_12w": [
        {"site_id": "Kanyama-HC", "week": "2026-W01", "value": 0},
        {"site_id": "Kanyama-HC", "week": "2026-W02", "value": 0},
        {"site_id": "Matero-L1", "week": "2026-W01", "value": 3},
        {"site_id": "Matero-L1", "week": "2026-W02", "value": 4},
    ],
    "diarrhoeal_4w": [
        {"site_id": "Kanyama-HC", "value": 23},
        {"site_id": "Matero-L1", "value": 41},
        {"site_id": "Chilenje-HC", "value": 8},
    ],
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    # --- Configuration from environment ---
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    if not api_key:
        print(
            "ERROR: No OpenAI API key found.\n"
            "Set the OPENAI_API_KEY environment variable and try again:\n"
            "\n"
            "    OPENAI_API_KEY=sk-... python demo.py\n"
        )
        sys.exit(1)

    # --- Import project components ---
    try:
        from open_sentinel.llm.openai_engine import OpenAIEngine
        from open_sentinel.testing.harness import SkillTestHarness
        from open_sentinel.types import AgentConfig
    except ImportError as exc:
        print(
            f"ERROR: Failed to import open-sentinel components: {exc}\n"
            "Make sure the package is installed:\n"
            "\n"
            "    pip install -e '.[dev]'\n"
        )
        sys.exit(1)

    # --- Load the cholera skill ---
    cholera_mod = _import_skill("idsr-cholera", "idsr_cholera_skill")
    skill = cholera_mod.IdsrCholeraSkill()

    # --- Create OpenAI engine ---
    try:
        engine = OpenAIEngine(api_key=api_key, model_name=model)
    except Exception as exc:
        print(f"ERROR: Failed to create OpenAI engine: {exc}")
        sys.exit(1)

    # --- Header ---
    separator = "=" * 60
    print(separator)
    print(f"  OPEN-SENTINEL -- Clinical Surveillance Demo")
    print(f"  Model: {model} | Profile: cloud | Skill: {skill.name()}")
    print(separator)
    print()

    # --- Check LLM availability ---
    print("[Checking LLM availability...]")
    try:
        is_available = await engine.available()
    except Exception:
        is_available = False

    if is_available:
        print("  OpenAI API: connected")
    else:
        print(
            "  OpenAI API: NOT reachable\n"
            "  The demo will fall back to rule-based analysis.\n"
        )

    print()
    print("[Sending surveillance data to LLM for analysis...]")
    print()

    # --- Run via SkillTestHarness ---
    config = AgentConfig(state_db_path=":memory:", hardware="cloud")
    harness = SkillTestHarness(skill=skill, llm=engine, config=config)
    harness.set_data(SAMPLE_DATA).set_site_id("Kanyama-HC")

    try:
        result = await harness.run_async()
    except Exception as exc:
        print(f"ERROR: Analysis failed: {exc}")
        print()
        print("If this is a network or authentication error, verify your")
        print("OPENAI_API_KEY is valid and you have API access.")
        sys.exit(1)

    # --- Print results ---
    print("--- Results ---")
    print()
    print(f"  Reflections: {result.reflection_count}")
    print(f"  Degraded mode: {'Yes' if result.degraded else 'No'}")
    print()

    if not result.alerts:
        print("  No alerts generated.")
    else:
        for i, alert in enumerate(result.alerts, 1):
            severity_tag = alert.severity.upper()
            print(f"  ALERT {i} [{severity_tag}]")
            print(f"    Title:       {alert.title}")
            if alert.ai_confidence is not None:
                print(f"    Confidence:  {alert.ai_confidence}")
            if alert.ai_model:
                print(f"    Model:       {alert.ai_model}")
            if alert.description:
                # Wrap long descriptions
                desc = alert.description
                if len(desc) > 200:
                    desc = desc[:200] + "..."
                print(f"    Description: {desc}")
            if alert.evidence:
                print(f"    Evidence:    {alert.evidence}")
            if alert.measured_value is not None:
                print(f"    Measured:    {alert.measured_value}")
            if alert.threshold_value is not None:
                print(f"    Threshold:   {alert.threshold_value}")
            print(f"    Requires review: {'Yes' if alert.requires_review else 'No'}")
            print()

    # --- Provenance ---
    print("--- Provenance ---")
    if result.alerts:
        first = result.alerts[0]
        print(f"  AI generated:          {'Yes' if first.ai_generated else 'No'}")
        print(f"  Reflection iterations: {first.reflection_iterations}")
        print(f"  Rule validated:        {'Yes' if first.rule_validated else 'No'}")
    else:
        print("  No alerts to show provenance for.")
    print()

    # --- Token usage (from event bus history) ---
    total_tokens = 0
    for event in result.events:
        if event.get("event") == "llm.inference.completed":
            total_tokens += event.get("tokens", 0)

    # The test harness does not emit llm.inference events, so also note
    # that token tracking is best-effort here. If we found no events,
    # indicate that token data is not available through the harness.
    print("--- Token Usage ---")
    if total_tokens > 0:
        print(f"  Total tokens: {total_tokens}")
    else:
        print("  Token tracking: not available via test harness")
        print("  (Full token metrics are recorded in the agent runtime.)")
    print()

    print(separator)
    print("  Demo complete. All alerts carry requires_review=True.")
    print("  No automated clinical action is ever taken.")
    print(separator)


if __name__ == "__main__":
    asyncio.run(main())
