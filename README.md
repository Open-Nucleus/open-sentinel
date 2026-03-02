# open-sentinel

**LLM-powered sleeper agent for passive clinical surveillance over any health data source.**

open-sentinel runs offline on a Raspberry Pi with [Ollama](https://ollama.com) (phi3:mini / llama3.2) or connects to cloud LLM APIs. It sleeps until woken by data events, scheduled triggers, or manual requests — then routes clinical data through pluggable **skills** that combine LLM reasoning with rule-based safety nets to detect outbreaks, medication safety issues, stockouts, and more.

Every alert requires human review. No automated clinical action, ever.

---

## Key Features

- **Offline-first** — runs on Raspberry Pi 4 (8GB) with Ollama, no internet required
- **Dual-engine execution** — LLM reasoning as primary path, deterministic rules as fallback when LLM is unavailable
- **Reflection loop** — LLM findings are critiqued against actual data and refined (up to 3 iterations)
- **Hallucination detection** — evidence in alerts is cross-referenced against fetched data
- **Human-in-the-loop** — clinician feedback calibrates confidence thresholds over time
- **Pluggable skills** — each skill is a folder with `SKILL.md` (clinical context) + `skill.py` (logic)
- **Multi-source adapters** — FHIR, DHIS2, OpenMRS, SQLite, CSV
- **Multi-output alerts** — FHIR Flags, webhooks, SMS, email, console

## Architecture

```
Sleep → Wake → Route → Analyze → Alert → Sleep
```

### Core Loop

1. **Wake** — triggered by data events, cron schedule, or manual API call
2. **Route** — match event to skills by resource type + ICD code prefix
3. **Prioritize** — rank matched skills by clinical urgency (CRITICAL > HIGH > MEDIUM > LOW)
4. **Analyze** — per skill: fetch data → load memory → build prompt → LLM reasons → reflection loop → guardrails → deduplicate → emit alerts → store episode
5. **Sleep** — until next trigger

### Five Core Interfaces

| Interface | Role |
|-----------|------|
| `DataAdapter` | Read clinical data from any source (FHIR, DHIS2, OpenMRS, SQLite, CSV) |
| `LLMEngine` | Core reasoning — reason, reflect, explain, plan |
| `Skill` | Pluggable analysis unit with LLM + rule-based paths |
| `AlertOutput` | Emit alerts to targets (FHIR Flag, webhook, SMS, email, console) |
| `MemoryStore` | Four-tier memory — working, episodic, semantic, procedural (SQLite) |

### Safety Invariants

1. **`requires_review = True`** on every alert — enforced by model validator, cannot be overridden
2. **AI provenance tagging** — `ai_generated`, `ai_model`, `ai_confidence`, `reflection_iterations`, `rule_validated`
3. **Patient data isolation** — cloud LLMs never see patient identifiers
4. **Hallucination detection** — evidence cross-referenced against actual fetched data
5. **Confidence gating** — calibrated threshold (default 0.6, raised by false positive feedback, ceiling 0.95)
6. **Rate limiting** — max critical alerts per hour per skill

## Installation

```bash
# From source (editable mode)
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=open_sentinel --cov-report=term-missing

# Lint
ruff check open_sentinel/ tests/
```

### Requirements

- Python 3.11+
- For local LLM: [Ollama](https://ollama.com) with `phi3:mini` or `llama3.2`

## Quick Start

```python
import asyncio
from open_sentinel.agent import SentinelAgent
from open_sentinel.adapters import CsvAdapter
from open_sentinel.llm import OllamaEngine, MockLLMEngine
from open_sentinel.outputs import ConsoleOutput, FileOutput, WebhookOutput
from open_sentinel.types import AgentConfig

async def main():
    agent = SentinelAgent(
        data_adapter=CsvAdapter(
            directory="./data",
            resource_type_file_map={"Condition": "conditions.csv"},
        ),
        llm=OllamaEngine("http://localhost:11434"),  # or MockLLMEngine()
        skills=[IdsrCholeraSkill()],
        outputs=[
            ConsoleOutput(),
            FileOutput(path="alerts.jsonl"),
            WebhookOutput(url="https://hooks.example.com/alerts"),
        ],
        config=AgentConfig(hardware="pi4_8gb"),
    )
    await agent.start()
    await agent.run()

asyncio.run(main())
```

## Data Adapters

| Adapter | Source | Key Features |
|---------|--------|--------------|
| `CsvAdapter` | CSV/TSV files in a directory | Resource type → file mapping, in-memory filtering |
| `SqliteAdapter` | User-managed SQLite DB | WAL mode, SQL-level filtering and aggregation |
| `FhirGitAdapter` | FHIR JSON in a Git repo | SQLite index for fast queries, loads full JSON on demand |

## Alert Outputs

| Output | Target | Key Features |
|--------|--------|--------------|
| `ConsoleOutput` | stdout | Plain text or JSON format |
| `FileOutput` | JSON Lines file | Append-only, severity filtering |
| `WebhookOutput` | HTTP endpoint | HMAC-SHA256 signing, severity filtering, failure tolerance |

## Built-in IDSR Skills

Five WHO IDSR epidemic surveillance skills, all built on `IdsrBaseSkill`:

| Skill | ICD-10 | Threshold | Confidence |
|-------|--------|-----------|------------|
| `idsr-cholera` | A00 | Zero-to-one → critical, 2× baseline → high | 0.7 |
| `idsr-measles` | B05 | Zero-to-one → critical, ≥3 cluster → critical | 0.7 |
| `idsr-meningitis` | A39, G00, G01 | Seasonal thresholds, off-season ≥2 → critical | 0.7 |
| `idsr-yellow-fever` | A95 | Zero tolerance — any case → critical | 0.8 |
| `idsr-ebola` | A98.3, A98.4 | Zero tolerance + hemorrhagic sentinel | 0.85 |

Each skill has dual-engine execution (LLM primary, rule-based fallback) and cross-references LLM findings against actual data via the reflection loop.

## Writing a Skill

Each skill is a folder: `skills/<name>/SKILL.md` + `skills/<name>/skill.py`.

### SKILL.md

YAML frontmatter with clinical context:

```yaml
---
name: idsr-cholera
priority: critical
trigger: both
schedule: "0 6 * * 1"
event_filter:
  resource_type: Condition
  code_prefix: "A00"
requires:
  resources: [Condition]
  llm: true
  adapter_features: [aggregate]
  min_data_window: 12w
goal: Detect cholera outbreaks within 24 hours
max_reflections: 2
confidence_threshold: 0.7
---

## Clinical Background
Cholera (ICD-10: A00) is an acute diarrheal disease...

## Reasoning Instructions
Compare current case counts against seasonal baselines...

## Rule-Based Fallback
baseline == 0 AND count >= 1 → CRITICAL; count > baseline * 2 → HIGH
```

### skill.py

```python
from open_sentinel.skills.idsr_base import IdsrBaseSkill
from open_sentinel.types import Alert, AnalysisContext, DataRequirement

class IdsrCholeraSkill(IdsrBaseSkill):
    def name(self) -> str:
        return "idsr-cholera"

    def required_data(self) -> dict[str, DataRequirement]:
        return {
            "cholera_this_week": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A00"},
                time_window="1w",
                group_by=["site_id"],
                metric="count",
            ),
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        counts = self._site_counts(ctx, "cholera_this_week")
        return f"Analyze cholera data: {counts}"

    def rule_fallback(self, ctx: AnalysisContext) -> list[Alert]:
        counts = self._site_counts(ctx, "cholera_this_week")
        alerts = []
        for site_id, count in counts.items():
            baseline = ctx.baselines.get(f"cholera-{site_id}", 0)
            if baseline == 0 and count >= 1:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    title=f"Cholera at {site_id} (zero baseline)",
                    rule_validated=True,
                ))
        return alerts
```

## Testing Skills

Use the built-in `SkillTestHarness` for three test patterns:

```python
from open_sentinel.testing import SkillTestHarness, MockLLMEngine

# Pattern 1: LLM path with reflection
async def test_llm_with_reflection():
    llm = MockLLMEngine(responses=[
        {"findings": [{"severity": "critical", "title": "Outbreak", "confidence": 0.9}]}
    ])
    harness = SkillTestHarness(skill=CholeraSkill(), llm=llm)
    harness.set_data({"cases": [{"id": "1"}, {"id": "2"}, {"id": "3"}]})
    result = await harness.run_async()
    assert not result.degraded
    assert result.alerts[0].ai_generated is True

# Pattern 2: Hallucination detection (reflection catches fabricated data)
# Pattern 3: Degraded mode (no LLM, rules only)
async def test_degraded():
    llm = MockLLMEngine(is_available=False)
    harness = SkillTestHarness(skill=CholeraSkill(), llm=llm)
    harness.set_data({"cases": [{"id": str(i)} for i in range(5)]})
    result = await harness.run_async()
    assert result.degraded is True
    assert result.alerts[0].rule_validated is True
```

## Hardware Profiles

| Profile | LLM | Concurrent Skills | Max Reflections | Model |
|---------|-----|-------------------|-----------------|-------|
| `pi4_4gb` | No | 4 | 0 | None (rules only) |
| `pi4_8gb` | Yes | 2 | 2 | phi3:mini |
| `hub_16gb` | Yes | 4 | 3 | llama3.2:3b |
| `hub_32gb` | Yes | 8 | 3 | llama3.2:8b |

## Memory System

SQLite-backed, four tiers:

- **Working** — current run only (in-memory dict)
- **Episodic** — past analyses + outcomes (what happened last time at this site?)
- **Semantic** — baselines + site profiles (what's normal for this location?)
- **Procedural** — calibrated thresholds (how cautious should this skill be?)

## Feedback Loop

Every alert enters a review queue. Clinician feedback calibrates skill behavior:

- **Dismissed** (false positive) → confidence threshold raised by 0.05 (capped at 0.95)
- **Confirmed** → timestamp recorded for future reference

The agent learns to be more cautious where it makes mistakes, but can never gate itself into silence.

## Project Structure

```
open_sentinel/
├── agent.py              # SentinelAgent: core loop
├── interfaces.py         # 5 ABCs (DataAdapter, LLMEngine, Skill, AlertOutput, MemoryStore)
├── types.py              # Pydantic v2 models (Alert, DataEvent, Episode, etc.)
├── time_utils.py         # Time window parser + epiweek calculator
├── memory.py             # SqliteMemoryStore
├── registry.py           # SkillRegistry: SKILL.md parsing, event matching
├── reflection.py         # Critique → reflect loop
├── guardrails.py         # Confidence gate, hallucination detection, rate limiting
├── feedback.py           # Human-in-the-loop calibration
├── events.py             # EventBus: lifecycle events
├── hooks.py              # HookRegistry: 11 extension points
├── priority.py           # Skill + alert ranking
├── resources.py          # Hardware profiles, LLM semaphore
├── dedup.py              # Alert deduplication
├── scheduler.py          # Cron-based scheduling
├── adapters/
│   ├── csv_adapter.py    # CsvAdapter: CSV/TSV files
│   ├── sqlite_adapter.py # SqliteAdapter: clinical SQLite DBs
│   └── fhir_git.py       # FhirGitAdapter: FHIR JSON + SQLite index
├── llm/
│   ├── mock.py           # MockLLMEngine for testing
│   └── ollama.py         # OllamaEngine (OpenAI-compatible API)
├── outputs/
│   ├── console.py        # Console alert output
│   ├── file_output.py    # JSON Lines file output
│   └── webhook.py        # HTTP webhook output (HMAC-SHA256)
├── skills/
│   └── idsr_base.py      # IdsrBaseSkill: shared base for IDSR skills
└── testing/
    ├── harness.py        # SkillTestHarness
    ├── fixtures.py       # make_data_event(), make_alert(), make_episode()
    └── mock_llm.py       # Re-exports MockLLMEngine

skills/                   # Deployed skill folders (SKILL.md + skill.py each)
├── idsr-cholera/         # Cholera outbreak detection (A00)
├── idsr-measles/         # Measles outbreak detection (B05)
├── idsr-meningitis/      # Meningitis detection with seasonal awareness (A39)
├── idsr-yellow-fever/    # Yellow fever zero-tolerance detection (A95)
└── idsr-ebola/           # Ebola + hemorrhagic fever sentinel (A98)
```

## Roadmap

- **Phase 1** ✅ — Core framework, agent loop, memory, reflection, guardrails, test harness
- **Phase 2** ✅ — Data adapters (FHIR Git, SQLite, CSV), 5 IDSR skills, file/webhook outputs
- **Phase 3** — Medication, stockout, immunisation, TB, maternal skills, SMS output, full feedback loop
- **Phase 4** — Syndromic surveillance, SentinelHub skill registry, DHIS2/OpenMRS adapters
- **Phase 5** — Documentation, evaluation framework, Pi 4 deployment guide

## License

[Apache 2.0](LICENSE)
