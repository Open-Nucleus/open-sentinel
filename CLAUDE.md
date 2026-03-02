# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

open-sentinel is an LLM-powered sleeper agent for passive clinical surveillance over any health data source. It runs offline on a Raspberry Pi with Ollama (phi3:mini / llama3.2) or connects to cloud LLM APIs. Skills are the intelligence units — each is a folder with `SKILL.md` (clinical context + YAML frontmatter) and `skill.py` (logic). The LLM is the core reasoning engine, not a feature; rule-based thresholds are the safety-net fallback when the LLM is unavailable.

**Spec:** `open-sentinel-spec.md` is the canonical design document (v0.3.1). All implementation must conform to it.

## Build & Development Commands

```bash
# Install (editable mode)
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run a single test
pytest tests/test_skills.py::test_cholera_llm_with_reflection -v

# Run the agent
sentinel run --config config.yaml

# Skill management CLI
sentinel install <skill-name>
sentinel test ./skills/<skill-name>/
sentinel publish ./skills/<skill-name>/
sentinel search --category epidemic --region sub-saharan-africa
```

## Architecture

### Core Loop: Sleep → Wake → Route → Analyze → Alert → Sleep

The agent does no work until woken by one of three triggers: **data events** (adapter pushes `DataEvent`), **schedule** (cron), or **manual** (HTTP API / CLI). On wake:

1. **Routing** — match event to skills by resource type + ICD code prefix
2. **Prioritization** — rank matched skills by clinical urgency (`CRITICAL > HIGH > MEDIUM > LOW`)
3. **Parallelization** — run independent skills concurrently (but serialize LLM access on Pi)
4. **Per-skill pipeline:** fetch data → load memory → build prompt → LLM reasons → reflection loop → guardrails → deduplicate → emit alerts → store episode

### Five Core Interfaces (`open_sentinel/interfaces.py`)

| Interface | Role | Implementations |
|-----------|------|-----------------|
| `DataAdapter` | Read clinical data from any source | `FhirGitAdapter`, `FhirHttpAdapter`, `Dhis2Adapter`, `OpenMrsAdapter`, `SqliteAdapter`, `CsvAdapter` |
| `LLMEngine` | Core reasoning (reason, reflect, explain, plan) | `OllamaEngine` (primary/offline), `OpenAIEngine`, `AnthropicEngine`, `MockEngine` |
| `Skill` | Pluggable analysis unit | 16 built-in skills in `skills/` directory |
| `AlertOutput` | Emit alerts to targets | `FhirFlagOutput`, `WebhookOutput`, `SmsOutput`, `EmailOutput`, `FileOutput`, `ConsoleOutput`, etc. |
| `MemoryStore` | Three-tier memory (working/episodic/semantic/procedural) | SQLite-backed, 5 tables |

### Dual-Engine Execution

Every skill has two paths:
- **LLM path** (primary): `build_prompt()` → `llm.reason()` → `critique_findings()` reflection loop → guardrails → emit
- **Rule path** (degraded): `rule_fallback()` → deterministic threshold rules when LLM is unavailable

### Reflection Loop (Pattern 4)

After LLM generates findings, `critique_findings()` validates against rules/data. If critique != "ACCEPT", `llm.reflect()` refines findings. Max iterations: 2 on Pi, 3 on hub. Capped by `ResourceManager`.

### Key Types (`open_sentinel/types.py`)

- `DataEvent` — emitted by adapters on new/modified data
- `DataRequirement` — declares what data a skill needs (resource type, filters, time window, grouping, metric)
- `AnalysisContext` — everything a skill receives (trigger, data, LLM, memory, episodes, baselines, config)
- `Alert` — output of analysis; always carries AI provenance fields and `requires_review: True`
- `Episode` — record of a past analysis for episodic memory
- `InvestigationPlan` / `InvestigationStep` — multi-step plans from LLM (syndromic surveillance)

### Memory System (`open_sentinel/memory.py`)

SQLite-backed, four tiers:
- **Working** — current run only (in-memory dict)
- **Episodic** — past analyses + outcomes (persisted)
- **Semantic** — baselines + site profiles (persisted)
- **Procedural** — calibrated thresholds (persisted)

Tables: `episodes`, `baselines`, `skill_state`, `alert_history`, `emission_queue`. TEXT PKs (UUIDs), TEXT timestamps (ISO 8601).

## Safety Invariants (Non-Negotiable)

1. **`requires_review = True` on every alert.** No automated clinical action, ever.
2. **AI provenance tagging** on every LLM-involved alert: `ai_generated`, `ai_model`, `ai_confidence`, `reflection_iterations`, `rule_validated`.
3. **Patient data isolation** — cloud LLMs never see patient identifiers. Only local Ollama may use `allow_patient_data: true`.
4. **Hallucination detection** — evidence cross-referenced against actual fetched data in both reflection (`critique_findings`) and guardrails (`_evidence_exists_in_data`).
5. **Confidence gating** — calibrated threshold (default 0.6, raised by false positive feedback, ceiling 0.95).
6. **Rate limiting** — max critical alerts per hour per skill.

## Skill Authoring

Each skill is a folder: `skills/<name>/SKILL.md` + `skills/<name>/skill.py`.

**SKILL.md** has YAML frontmatter (name, priority, trigger, schedule, event_filter, requires, goal, success_criteria, max_reflections, confidence_threshold, metadata) followed by markdown sections: Clinical Background, Reasoning Instructions, Rule-Based Fallback.

**skill.py** implements the `Skill` ABC. Required methods: `name()`, `required_data()`, `build_prompt(ctx)`, `rule_fallback(ctx)`. Optional overrides: `critique_findings()`, `response_schema()`, `can_request_additional_data()`.

Skill precedence: built-in (lowest) → community `~/.sentinel/skills/` → deployment `<config_dir>/skills/` (highest).

## Testing

Use `SkillTestHarness` from `open_sentinel.testing` with `MockLLMEngine` for skill tests. Three test patterns per skill:
1. LLM path with reflection validation
2. Hallucination detection (LLM fabricates data, reflection catches it)
3. Degraded mode (no LLM, rules-only fallback)

## Hardware Profiles

| Profile | LLM | Concurrent Skills | Max Reflections | Model |
|---------|-----|-------------------|-----------------|-------|
| `pi4_4gb` | No | 4 | 0 | None (rules only) |
| `pi4_8gb` | Yes | 2 | 2 | phi3:mini |
| `hub_16gb` | Yes | 4 | 3 | llama3.2:3b |
| `hub_32gb` | Yes | 8 | 3 | llama3.2:8b |

## Event System

`EventBus` emits lifecycle events (e.g., `agent.started`, `skill.completed`, `alert.emitted`, `llm.inference.completed`). `HookRegistry` provides extension points (`before_data_fetch`, `before_skill_run`, `before_alert_emit`, `on_reflection`, `on_feedback`, etc.).

## Feedback Loop (Human-in-the-Loop)

Every alert enters a review queue. Clinician feedback (`confirmed`/`dismissed`) calibrates skill confidence thresholds via procedural memory. Dismissed alerts raise the threshold by 0.05 (capped at 0.95).
