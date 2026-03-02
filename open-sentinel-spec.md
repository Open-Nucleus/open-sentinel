# open-sentinel

**An LLM-powered sleeper agent for passive clinical surveillance over any health data source.**

**Repo:** github.com/Open-Nucleus/open-sentinel  
**Licence:** Apache 2.0  
**Author:** Dr Akanimoh Osutuk — FibrinLab  
**Version:** 0.3.1 (Draft Specification)  
**Date:** March 2026

---

## 1. The Problem

### 1.1 What Exists Today

**DHIS2 Tracker** — the WHO's health information platform used in 80+ countries. Retrospective dashboards, not real-time surveillance agents. Tells you what happened. Doesn't wake you up when something is happening.

**ProMED / HealthMap / EIOS** — global epidemic intelligence. Macro-level (country/region), require internet, don't operate on facility-level clinical data.

**Custom scripts in EHRs** — hardcoded SQL, not portable, not shareable, break when schemas change.

**Commercial CDS** — Epic's BPA, Cerner's MPages. Proprietary, expensive, US/European-focused, require always-on servers and internet.

### 1.2 The Gap

No existing open-source project provides a **lightweight, LLM-powered, offline-capable surveillance agent** that:

1. **Thinks about clinical data, not just queries it.** The LLM is the core intelligence — reasoning over patterns, cross-referencing signals, generating natural language explanations. Rule-based thresholds are the safety net, not the product.
2. **Sleeps until woken.** No polling, no cron jobs. Wakes on data events or configurable schedules.
3. **Runs analysis through pluggable skills.** Each skill is a folder with a `SKILL.md` and `skill.py`. Community-contributed, independently testable.
4. **Reads from any health data source.** FHIR R4, DHIS2, OpenMRS, SQLite, CSV. Pluggable adapters.
5. **Emits alerts to any target.** FHIR DetectedIssue, DHIS2 events, SMS, webhooks. Pluggable outputs.
6. **Runs on a Raspberry Pi with a local LLM.** Ollama with phi3:mini or llama3.2. No internet required.

open-sentinel is the agent framework. Skills are the intelligence. The LLM is the brain. Anyone can write a skill.

---

## 2. Agentic Design Patterns

open-sentinel is built on 21 agentic design patterns (Gulli, *Agentic Design Patterns*, 2026). Each pattern maps to a specific layer and responsibility in sentinel's architecture.

### 2.1 Pattern Map

| # | Pattern | Layer | Role in Sentinel |
|---|---------|-------|-----------------|
| 1 | **Prompt Chaining** | Skill | Skills chain: data fetch → context build → LLM reasoning → structured findings → alert generation. |
| 2 | **Routing** | Framework | Event routing: agent wakes, matches events to skills by resource type, ICD code prefix, and event type. |
| 3 | **Parallelization** | Framework | Independent skills run concurrently. Data fetches for independent requirements happen in parallel. LLM access is serialised on constrained hardware. |
| 4 | **Reflection** | Framework + Skill | Iterative loop: LLM generates findings → skill critiques against rules → LLM refines. Max 2 iterations on Pi, 3 on hub. |
| 5 | **Tool Use** | Framework | Skills can request additional data queries mid-analysis. The LLM's findings may include `additional_data_needed` which triggers a follow-up fetch and re-analysis. |
| 6 | **Planning** | Skill | Syndromic surveillance asks the LLM to plan an investigation — "what additional data would confirm this pattern?" — then executes the plan. |
| 7 | **Multi-Agent** | Future | Hub-level sentinel with specialist sub-agents (epidemic, medication safety, supply chain). Cross-reference findings across domains. |
| 8 | **Memory** | Framework | Three-tier: working (current run), episodic (past analyses + outcomes), semantic (baselines + site profiles), procedural (calibrated thresholds). |
| 9 | **Learning/Adaptation** | Framework | Clinician feedback (confirmed/dismissed) adjusts confidence thresholds. False positives increase the gate. Confirmed alerts reinforce. |
| 10 | **MCP** | Future | Model Context Protocol for sentinel to expose tools to external agents and consume external data sources as tools. |
| 11 | **Goal Setting** | Skill | Each skill declares a goal ("detect cholera outbreaks within 24h of first case") with measurable success criteria. Agent tracks achievement. |
| 12 | **Exception Handling** | Framework | LLM unavailable → rule fallback. Adapter failure → retry with exponential backoff. Output failure → emission queue. Skill exception → isolate, log, continue others. |
| 13 | **Human-in-the-Loop** | Framework | Every alert enters a review queue. Clinician feedback flows back to calibrate skills. No automated clinical action ever. |
| 14 | **RAG** | Skill | Skills are RAG pipelines: retrieve clinical data, augment LLM context with SKILL.md domain knowledge, generate findings. |
| 15 | **Inter-Agent (A2A)** | Future | Federated sentinel agents at different sites sharing aggregated, anonymised findings via the Open Nucleus sync protocol. |
| 16 | **Resource-Aware** | Framework | LLM inference scheduling on constrained hardware. Priority queue for skills. Fewer reflection iterations on Pi. Adaptive model selection. |
| 17 | **Reasoning** | Skill | SKILL.md encodes chain-of-thought reasoning instructions. The LLM is told HOW to reason about the data, not just WHAT to look for. |
| 18 | **Guardrails/Safety** | Framework | Hallucination detection via data cross-reference. Confidence gating. `ai_generated` tagging. Rate limiting. Clinical action prohibition. |
| 19 | **Evaluation** | Framework | Lifecycle events, alert outcome tracking, skill performance metrics (precision, recall over time), LLM accuracy monitoring. |
| 20 | **Prioritization** | Framework | Skill execution ordered by clinical urgency. Alert emission routed by severity (critical → SMS, moderate → webhook). LLM slot allocation to highest-priority skill first. |
| 21 | **Exploration** | Skill | Syndromic surveillance: LLM looks for patterns the pre-defined skills haven't anticipated. Open-ended epidemiological reasoning. |

### 2.2 Pattern Interaction Flow

```
Wake Trigger (Event / Schedule / Manual)
    │
    ▼
[ROUTING] ── Match event to skills by resource type + ICD code
    │
    ▼
[PRIORITIZATION] ── Rank matched skills by clinical urgency
    │
    ▼
[PARALLELIZATION] ── Run independent skills concurrently
    │                  (serialise LLM access on Pi)
    ▼ (per skill)
[PROMPT CHAINING] ── Fetch data → Load memory → Build prompt → LLM reasons
    │
    ├─ [RAG] Retrieve clinical data via DataAdapter
    ├─ [MEMORY] Inject episodic context + baselines
    ├─ [REASONING] SKILL.md chain-of-thought instructions
    ├─ [TOOL USE] LLM requests additional data → follow-up fetch
    └─ [PLANNING] LLM plans multi-step investigation (syndromic only)
    │
    ▼
[REFLECTION] ── critique_findings() → below confidence? → LLM refines → repeat
    │              (max 2 iterations Pi, 3 hub)
    ▼
[GUARDRAILS] ── Hallucination check, confidence gate, rate limit, safety invariants
    │
    ▼
[HUMAN-IN-THE-LOOP] ── Alert → review queue → clinician decides
    │
    ▼
[LEARNING] ── Clinician feedback → update episodic memory + calibrate thresholds
    │
    ▼
[EVALUATION] ── Track alert outcomes, measure skill precision/recall
    │
    ▼
[EXCEPTION HANDLING] ── At every step: retry / degrade / queue / log
    │
    ▼
[RESOURCE-AWARE] ── Throughout: manage LLM slots, RAM, inference budget
```

---

## 3. Architecture

### 3.1 LLM-First Design

The LLM is not a feature. It is the core of the agent.

```
                    ┌──────────────────────────────────┐
                    │          open-sentinel            │
                    │                                    │
                    │  ┌────────────────────────────┐   │
  Data Sources      │  │       LLM Engine            │   │  Alert Targets
  ──────────────────┤  │    (Ollama / Cloud API)     │   ├──────────────
  FHIR R4       ───▶│  │                            │   │──▶ FHIR Flag
  DHIS2         ───▶│  │  ┌─────────┐ ┌─────────┐  │   │──▶ SMS
  OpenMRS       ───▶│  │  │ Skill A │ │ Skill B │  │   │──▶ Webhook
  SQLite/CSV    ───▶│  │  │ Skill C │ │ Skill D │  │   │──▶ Email
                    │  │  └─────────┘ └─────────┘  │   │──▶ DHIS2
                    │  │                            │   │
                    │  │  ┌──────────────────────┐  │   │
                    │  │  │      Memory          │  │   │
                    │  │  │ Working │ Episodic   │  │   │
                    │  │  │ Semantic│ Procedural │  │   │
                    │  │  └──────────────────────┘  │   │
                    │  └────────────────────────────┘   │
                    │                                    │
                    │  ┌────────────────────────────┐   │
                    │  │  Sleeper │ Priority Queue  │   │
                    │  │  Loop    │ Resource Mgr    │   │
                    │  └────────────────────────────┘   │
                    └──────────────────────────────────┘
```

### 3.2 Dual-Engine with Reflection Loop

```
Skill triggered
    │
    ├─ LLM available?
    │   │
    │   ├─ YES → LLM Path (primary)
    │   │   ├─ Fetch data via DataAdapter
    │   │   ├─ Load episodic context from memory
    │   │   ├─ Build clinical context prompt (SKILL.md + data + episodes)
    │   │   ├─ LLM reasons → structured findings
    │   │   │
    │   │   ├─ REFLECTION LOOP ◄───────────────────────────┐
    │   │   │   ├─ critique_findings() validates against rules      │
    │   │   │   ├─ All findings pass? ──YES──▶ ACCEPT              │
    │   │   │   └─ Findings fail? ──NO──▶ LLM.reflect() ──────────┘
    │   │   │       (critique + original context → refined findings)
    │   │   │       (max 2 iterations Pi, 3 hub)
    │   │   │
    │   │   ├─ Guardrail pipeline (confidence gate, hallucination check)
    │   │   ├─ Deduplicate → Prioritise → Emit to outputs + review queue
    │   │   └─ Store episode in memory
    │   │
    │   └─ NO → Rule Path (degraded mode)
    │       ├─ Fetch data, apply threshold rules
    │       ├─ Generate template alerts tagged "rule-only"
    │       └─ Queue LLM explanation for when engine returns
    │
    └─ Every alert carries:
        ├─ ai_generated, ai_confidence, ai_model, ai_reasoning
        ├─ rule_validated, reflection_iterations
        ├─ requires_review: true (always)
        └─ outcome: pending (updated when clinician reviews)
```

### 3.3 The Sleeper Loop

The agent does no work until woken. Three wake triggers:

| Trigger | Example | Implementation |
|---------|---------|----------------|
| **Event** | Sync completed, new resource created | DataAdapter pushes DataEvent to agent |
| **Schedule** | Every 6 hours, daily at 06:00, weekly Monday | Internal cron scheduler |
| **Manual** | Clinician requests analysis, admin triggers sweep | HTTP API / CLI |

---

## 4. Core Types

### 4.1 DataEvent

```python
@dataclass
class DataEvent:
    """Emitted by DataAdapter when new or modified data arrives."""
    event_type: str          # "resource.created", "resource.updated", "sync.completed"
    resource_type: str       # "Condition", "MedicationRequest", "Observation"
    resource_id: Optional[str] = None
    resource_data: Optional[Dict[str, Any]] = None
    site_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None
```

### 4.2 DataRequirement

```python
@dataclass
class DataRequirement:
    """Declares what data a skill needs."""
    resource_type: str
    filters: Dict[str, Any]
    time_window: Optional[str] = None    # "12w", "4w", "7d", "24h"
    group_by: Optional[List[str]] = None
    metric: Optional[str] = None         # "count", "sum", "avg", "latest"
    limit: Optional[int] = None
    name: Optional[str] = None           # Key in ctx.data
```

### 4.3 AnalysisContext

```python
@dataclass
class AnalysisContext:
    """Everything a skill needs to perform analysis."""
    trigger: str                        # "event", "schedule", "manual"
    trigger_event: Optional[DataEvent]
    data: Dict[str, Any]                # Fetched data, keyed by DataRequirement name
    site_id: Optional[str]
    config: Dict[str, Any]              # Skill-specific configuration
    llm: LLMEngine
    memory: MemoryStore
    episodes: List[Episode]             # Past analyses at this site for this skill
    baselines: Dict[str, float]         # Semantic memory: learned baseline values
    previous_alerts: List[Alert]        # Recent alerts from this skill
```

### 4.4 LLMResponse

```python
@dataclass
class LLMResponse:
    text: str
    structured: Optional[Dict[str, Any]]
    model: str
    confidence: Optional[float]
    tokens_used: int
    duration_ms: int
```

### 4.5 Alert

```python
@dataclass
class Alert:
    # Identity
    id: str = field(default_factory=lambda: str(uuid4()))
    skill_name: str = ""
    severity: str = "moderate"         # critical, high, moderate, low
    category: str = ""                 # outbreak, medication-safety, stockout, etc.
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
    
    # LLM provenance (present on EVERY alert)
    ai_generated: bool = False
    ai_confidence: Optional[float] = None
    ai_model: Optional[str] = None
    ai_reasoning: Optional[str] = None
    rule_validated: bool = False
    reflection_iterations: int = 0
    requires_review: bool = True       # ALWAYS TRUE. Non-negotiable.
    
    # Outcome (updated by clinician feedback)
    outcome: str = "pending"           # pending, confirmed, dismissed, modified
    clinician_feedback: Optional[str] = None
    
    # Deduplication
    dedup_key: Optional[str] = None
    
    # FHIR mapping
    fhir_resource_type: str = "DetectedIssue"
    fhir_code: Optional[str] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = None
```

### 4.6 Episode

```python
@dataclass
class Episode:
    """A record of a past analysis for episodic memory."""
    id: str = field(default_factory=lambda: str(uuid4()))
    skill_name: str = ""
    site_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trigger: str = ""
    findings_summary: str = ""
    alerts_generated: int = 0
    outcome: str = "pending"
    clinician_feedback: Optional[str] = None
    data_snapshot: Optional[Dict] = None    # Compact summary, not full data
```

### 4.7 InvestigationPlan (Pattern 6: Planning)

```python
@dataclass
class InvestigationPlan:
    """A multi-step investigation plan generated by the LLM."""
    goal: str
    steps: List[InvestigationStep]
    estimated_data_requirements: List[DataRequirement]
    rationale: str

@dataclass
class InvestigationStep:
    description: str
    data_needed: Optional[DataRequirement]
    analysis_question: str
    depends_on: Optional[str] = None    # ID of a previous step
```

---

## 5. The Five Interfaces

### 5.1 DataAdapter — Where Data Lives

```python
class DataAdapter(ABC):
    """Read clinical data from any source.
    Skills use adapters as tools — including mid-analysis follow-up queries."""
    
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    async def query(self, resource_type: str, filters: Dict[str, Any],
                    limit: Optional[int] = None) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def count(self, resource_type: str, filters: Dict[str, Any]) -> int: ...
    
    @abstractmethod
    async def subscribe(self, event_types: List[str]) -> AsyncIterator[DataEvent]: ...
    
    @abstractmethod
    async def aggregate(self, resource_type: str, group_by: List[str],
                        metric: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]: ...
    
    def supports(self, feature: str) -> bool:
        """Check if adapter supports a feature (aggregate, subscribe, etc.)."""
        return feature in self._supported_features
    
    def has_resource_type(self, resource_type: str) -> bool:
        """Check if data source has this FHIR resource type."""
        return True  # Override for sources with known schemas
```

**Adapters:** `FhirGitAdapter`, `FhirHttpAdapter`, `Dhis2Adapter`, `OpenMrsAdapter`, `SqliteAdapter`, `CsvAdapter`

### 5.2 LLMEngine — The Core Intelligence

```python
class LLMEngine(ABC):
    """The core reasoning engine. Not optional."""
    
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def model(self) -> str: ...
    
    @abstractmethod
    async def reason(self, system_prompt: str, clinical_context: str,
                     question: str, schema: Optional[Dict] = None) -> LLMResponse:
        """Primary reasoning call. Skill builds the context, LLM thinks."""
        ...
    
    @abstractmethod
    async def reflect(self, original_findings: List[Dict], critique: str,
                      clinical_context: str, schema: Optional[Dict] = None) -> LLMResponse:
        """Pattern 4: Reflection. Refine findings based on critique from rules."""
        ...
    
    @abstractmethod
    async def explain(self, alert: Alert, context: str) -> str:
        """Generate natural language explanation for any alert.
        Called for every alert, including rule-only alerts in degraded mode
        (queued for when LLM returns)."""
        ...
    
    @abstractmethod
    async def plan(self, goal: str, available_data: List[str],
                   constraints: Dict) -> InvestigationPlan:
        """Pattern 6: Planning. Generate a multi-step investigation plan."""
        ...
    
    @abstractmethod
    async def available(self) -> bool:
        """Is the LLM ready to accept inference requests?"""
        ...
```

**Engines:** `OllamaEngine` (primary, offline), `OpenAIEngine`, `AnthropicEngine`, `MockEngine`

### 5.3 Skill — Teaching the LLM How to Think

Each skill is a folder: `SKILL.md` (clinical context + metadata) + `skill.py` (logic).

```python
class Skill(ABC):
    
    # ── Identity ──
    @abstractmethod
    def name(self) -> str: ...
    def trigger(self) -> SkillTrigger: ...             # EVENT, SCHEDULE, BOTH, MANUAL
    def schedule(self) -> Optional[str]: ...            # Cron expression
    def event_filter(self) -> Optional[Dict[str, Any]]: ...
    def priority(self) -> Priority: ...                 # CRITICAL, HIGH, MEDIUM, LOW
    
    # ── Pattern 14: RAG — Data requirements ──
    @abstractmethod
    def required_data(self) -> Dict[str, DataRequirement]: ...
    
    # ── Pattern 1+17: Prompt Chaining + Reasoning — LLM-first path ──
    @abstractmethod
    def build_prompt(self, ctx: AnalysisContext) -> str:
        """Build clinical context prompt for LLM reasoning.
        This is the primary analysis path."""
        ...
    
    def response_schema(self) -> Optional[Dict]:
        """JSON schema for structured LLM output.
        None = free-form text response."""
        return None
    
    # ── Pattern 4: Reflection ──
    def critique_findings(self, findings: List[Dict], ctx: AnalysisContext) -> str:
        """Critique LLM findings for the reflection loop.
        Return "ACCEPT" if findings pass validation.
        Return a critique string if findings need refinement.
        Default implementation: validate against rule thresholds."""
        return self._default_rule_critique(findings, ctx)
    
    def max_reflections(self) -> int:
        """Max reflection iterations. Resource manager may cap this lower."""
        return 2
    
    # ── Pattern 12: Exception Handling — Rule fallback ──
    @abstractmethod
    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        """Deterministic rules for when LLM is unavailable.
        This is degraded mode — safety net only."""
        ...
    
    # ── Pattern 11: Goal Setting ──
    def goal(self) -> str:
        """What this skill is trying to achieve."""
        return ""
    
    def success_criteria(self) -> Dict:
        """Measurable criteria. E.g. {"detection_window_hours": 24}"""
        return {}
    
    # ── Pattern 5+21: Tool Use + Exploration ──
    def can_request_additional_data(self) -> bool:
        """Can LLM findings include additional_data_needed requests?"""
        return False
    
    def handle_additional_data_request(self, request: Dict) -> DataRequirement:
        """Convert LLM's data request to a DataRequirement for fetching."""
        raise NotImplementedError
```

### 5.4 AlertOutput — Where Alerts Go

```python
class AlertOutput(ABC):
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    async def emit(self, alert: Alert) -> bool: ...
    @abstractmethod
    def accepts(self, alert: Alert) -> bool: ...
```

**Outputs:** `FhirFlagOutput`, `FhirHttpOutput`, `Dhis2EventOutput`, `WebhookOutput`, `SmsOutput`, `EmailOutput`, `FileOutput`, `ConsoleOutput`

### 5.5 MemoryStore — What the Agent Remembers (Pattern 8)

```python
class MemoryStore:
    """Three-tier memory for clinical surveillance context.
    Backed by SQLite. All operations are async for consistency."""
    
    # ── Working Memory (current run only, in-memory dict) ──
    async def get_working(self, key: str) -> Any: ...
    async def set_working(self, key: str, value: Any): ...
    async def clear_working(self): ...
    
    # ── Episodic Memory (past analyses + outcomes, persisted) ──
    async def store_episode(self, episode: Episode): ...
    async def recall_episodes(self, skill_name: str, site_id: str,
                               limit: int = 5) -> List[Episode]: ...
    async def update_episode_outcome(self, alert_id: str, outcome: str,
                                      feedback: str = None): ...
    
    # ── Semantic Memory (baselines + site profiles, persisted) ──
    async def get_baseline(self, skill_name: str, site_id: str,
                            metric: str) -> Optional[float]: ...
    async def update_baseline(self, skill_name: str, site_id: str,
                               metric: str, value: float): ...
    
    # ── Procedural Memory (calibrated thresholds, persisted) ──
    async def get_skill_state(self, skill_name: str, key: str) -> Any: ...
    async def set_skill_state(self, skill_name: str, key: str, value: Any): ...
    
    # ── Alert History ──
    async def store_alert(self, alert: Alert): ...
    async def get_alert(self, alert_id: str) -> Optional[Alert]: ...
    async def recent_alerts(self, skill_name: str, limit: int = 20) -> List[Alert]: ...
    async def update_alert_outcome(self, alert_id: str, outcome: str,
                                    feedback: str = None): ...
    async def count_recent_alerts(self, skill_name: str, severity: str = None,
                                   window_hours: int = 1) -> int: ...
    
    # ── Emission Queue ──
    async def queue_emission(self, alert_id: str, output_name: str, data: str): ...
    async def get_pending_emissions(self, limit: int = 50) -> List[Dict]: ...
    async def mark_emission_complete(self, emission_id: str): ...
    async def mark_emission_failed(self, emission_id: str, next_retry: datetime): ...
```

**SQLite schema:** 5 tables — `episodes`, `baselines`, `skill_state`, `alert_history`, `emission_queue`. See section 4.5 of the V3 draft for full DDL. All tables use TEXT primary keys (UUIDs) and TEXT timestamps (ISO 8601).

---

## 6. Agent Core

### 6.1 Initialization

```python
class SentinelAgent:
    
    def __init__(self, data_adapter, llm, skills, outputs, config=None):
        self.data = data_adapter
        self.llm = llm
        self.skill_registry = SkillRegistry(skills)
        self.outputs = outputs
        self.config = config or AgentConfig()
        self.memory = MemoryStore(self.config.state_db_path)
        self.scheduler = Scheduler()
        self.hooks = HookRegistry()
        self.events = EventBus()
        self.priority_queue = PriorityQueue()
        self.resource_manager = ResourceManager(self.config.hardware)
```

### 6.2 Sleeper Loop

```python
async def run(self):
    """Main loop. Blocks forever. Sleeps until woken."""
    self.events.emit("agent.started", {
        "skills": [s.name() for s in self.skill_registry.all()],
        "hardware": self.config.hardware,
    })
    
    # Register scheduled skills
    for skill in self.skill_registry.all():
        if skill.schedule():
            self.scheduler.register(skill.name(), skill.schedule(),
                                     lambda s=skill: self._run_skill(s))
    
    # Subscribe to data events
    async for event in self.data.subscribe(
        self.skill_registry.all_event_types()
    ):
        self.events.emit("agent.wake", {"trigger": "event", "event": event})
        
        try:
            await self._handle_event(event)
        except Exception as e:
            self.events.emit("agent.error", {"error": str(e)})
        
        # Process emission queue (retry failed outputs)
        await self._process_emission_queue()
        
        self.events.emit("agent.sleep", {
            "next_scheduled": self.scheduler.next_wake_time()
        })
```

### 6.3 Event Handling (Patterns 2, 3, 16, 20)

```python
async def _handle_event(self, event):
    # Pattern 2: Routing
    matched = self.skill_registry.match_event(event)
    if not matched:
        return
    
    # Pattern 20: Prioritization
    ranked = self.priority_queue.rank_skills(matched, event, self.resource_manager)
    
    # Pattern 3 + 16: Parallelization with resource awareness
    llm_available = await self.llm.available()
    
    if not llm_available:
        # All skills run degraded in parallel
        await asyncio.gather(*[
            self._run_rule_path(s, event) for s in ranked
        ])
        return
    
    # LLM available: run sequentially through priority queue
    # (only one inference at a time on Pi 4)
    for skill in ranked:
        if await self.resource_manager.should_defer_skill(skill):
            self.events.emit("skill.deferred", {"skill": skill.name()})
            continue
        
        await self.resource_manager.acquire_llm_slot()
        try:
            await self._run_skill(skill, event)
        except Exception as e:
            self.events.emit("skill.error", {
                "skill": skill.name(), "error": str(e)
            })
        finally:
            self.resource_manager.release_llm_slot()
```

### 6.4 Skill Execution — The Full Pipeline (Patterns 1, 4, 5, 8, 14, 17, 18)

```python
async def _run_skill(self, skill, trigger_event=None):
    run_id = generate_run_id()
    self.events.emit("skill.started", {
        "run_id": run_id, "skill": skill.name(), "priority": skill.priority().name
    })
    
    # ── FETCH DATA (Pattern 14: RAG) ──
    await self.hooks.run("before_data_fetch", skill)
    data = {}
    fetch_tasks = {
        name: self._fetch_data(req)
        for name, req in skill.required_data().items()
    }
    for name, task in fetch_tasks.items():
        data[name] = await task
    
    # ── LOAD MEMORY (Pattern 8) ──
    episodes = await self.memory.recall_episodes(skill.name(), self._current_site_id())
    baselines = {}
    for metric in skill.required_data().keys():
        bl = await self.memory.get_baseline(skill.name(), self._current_site_id(), metric)
        if bl is not None:
            baselines[metric] = bl
    
    ctx = AnalysisContext(
        trigger="event" if trigger_event else "schedule",
        trigger_event=trigger_event,
        data=data,
        site_id=self._current_site_id(),
        config=self.config.skill_config.get(skill.name(), {}),
        llm=self.llm,
        memory=self.memory,
        episodes=episodes,
        baselines=baselines,
        previous_alerts=await self.memory.recent_alerts(skill.name()),
    )
    
    # ── BUILD PROMPT + REASON (Pattern 1: Prompt Chaining, 17: Reasoning) ──
    await self.hooks.run("before_skill_run", skill, ctx)
    
    prompt = skill.build_prompt(ctx)
    schema = skill.response_schema()
    skill_md = self.skill_registry.get_skill_md(skill.name())
    system_prompt = self._build_system_prompt(skill_md, episodes)
    
    self.events.emit("llm.inference.started", {"run_id": run_id, "model": self.llm.model()})
    
    response = await self.llm.reason(
        system_prompt=system_prompt,
        clinical_context=prompt,
        question="Analyze this clinical data and report any findings.",
        schema=schema,
    )
    
    self.events.emit("llm.inference.completed", {
        "run_id": run_id, "duration_ms": response.duration_ms, "tokens": response.tokens_used
    })
    
    findings = self._parse_findings(response)
    
    # ── REFLECTION LOOP (Pattern 4) ──
    reflection_count = 0
    max_ref = min(skill.max_reflections(), self.resource_manager.max_reflections())
    
    while reflection_count < max_ref:
        critique = skill.critique_findings(findings, ctx)
        
        if critique == "ACCEPT":
            break
        
        self.events.emit("skill.reflecting", {
            "run_id": run_id, "iteration": reflection_count + 1,
            "critique_summary": critique[:200]
        })
        
        response = await self.llm.reflect(
            original_findings=findings,
            critique=critique,
            clinical_context=prompt,
            schema=schema,
        )
        findings = self._parse_findings(response)
        reflection_count += 1
    
    # ── TOOL USE: Additional data requests (Pattern 5) ──
    if skill.can_request_additional_data():
        for finding in findings:
            if "additional_data_needed" in finding:
                try:
                    req = skill.handle_additional_data_request(finding["additional_data_needed"])
                    ctx.data[req.name] = await self._fetch_data(req)
                    prompt = skill.build_prompt(ctx)
                    response = await self.llm.reason(
                        system_prompt=system_prompt,
                        clinical_context=prompt,
                        question="Re-analyze with the additional data.",
                        schema=schema,
                    )
                    findings = self._parse_findings(response)
                except Exception as e:
                    self.events.emit("skill.tool_use_error", {"run_id": run_id, "error": str(e)})
    
    # ── GUARDRAILS (Pattern 18) ──
    alerts = self._findings_to_alerts(findings, skill, response, reflection_count)
    alerts = await self._apply_guardrails(alerts, ctx)
    
    # ── DEDUPLICATE ──
    alerts = self._deduplicate(alerts)
    
    # ── PRIORITIZE + EMIT (Pattern 20) ──
    alerts = self.priority_queue.rank_alerts(alerts)
    
    await self.hooks.run("before_alert_emit", alerts)
    for alert in alerts:
        await self._emit_alert(alert)
    await self.hooks.run("after_alert_emit", alerts)
    
    # ── STORE EPISODE (Pattern 8: Memory) ──
    await self.memory.store_episode(Episode(
        skill_name=skill.name(),
        site_id=self._current_site_id(),
        trigger=ctx.trigger,
        findings_summary=self._summarize_findings(findings),
        alerts_generated=len(alerts),
    ))
    
    # ── LOG METRICS (Pattern 19: Evaluation) ──
    self.events.emit("skill.completed", {
        "run_id": run_id, "skill": skill.name(),
        "alerts": len(alerts), "reflections": reflection_count,
        "llm_tokens": response.tokens_used, "llm_duration_ms": response.duration_ms,
    })
```

### 6.5 System Prompt Construction (Pattern 17: Reasoning)

```python
def _build_system_prompt(self, skill_md, episodes):
    prompt = (
        "You are a clinical surveillance analyst running on an offline "
        "health data system deployed in resource-limited settings. "
        "You analyze patient data to detect disease outbreaks, medication "
        "safety issues, and clinical risks.\n\n"
        "Your findings will be reviewed by clinicians. Be precise, cite "
        "evidence from the data, state your confidence level (0.0-1.0), "
        "and explain your reasoning step by step.\n\n"
        f"## Skill Context\n{skill_md}\n\n"
    )
    
    if episodes:
        prompt += "## Past Analyses at This Site\n"
        for ep in episodes[-3:]:
            prompt += f"- {ep.timestamp:%Y-%m-%d}: {ep.findings_summary} (outcome: {ep.outcome})"
            if ep.clinician_feedback:
                prompt += f" — clinician: {ep.clinician_feedback}"
            prompt += "\n"
        prompt += "\n"
    
    return prompt
```

### 6.6 Degraded Mode (Pattern 12: Exception Handling)

```python
async def _run_rule_path(self, skill, trigger_event=None):
    """Fallback when LLM is unavailable."""
    run_id = generate_run_id()
    self.events.emit("skill.degraded", {
        "run_id": run_id, "skill": skill.name(), "reason": "llm_unavailable"
    })
    
    data = {}
    for name, req in skill.required_data().items():
        data[name] = await self._fetch_data(req)
    
    ctx = AnalysisContext(
        trigger="event" if trigger_event else "schedule",
        trigger_event=trigger_event,
        data=data,
        site_id=self._current_site_id(),
        config=self.config.skill_config.get(skill.name(), {}),
        llm=self.llm,
        memory=self.memory,
        episodes=[],
        baselines={},
        previous_alerts=await self.memory.recent_alerts(skill.name()),
    )
    
    alerts = skill.rule_fallback(ctx)
    
    for alert in alerts:
        alert.ai_generated = False
        alert.ai_reasoning = "[LLM unavailable — rule-based detection only]"
        alert.rule_validated = True
    
    alerts = self._deduplicate(alerts)
    for alert in alerts:
        await self._emit_alert(alert)
    
    self.events.emit("skill.completed", {
        "run_id": run_id, "skill": skill.name(),
        "alerts": len(alerts), "reflections": 0, "degraded": True,
    })
```

---

## 7. Human-in-the-Loop (Pattern 13) and Learning (Pattern 9)

### 7.1 The Review Queue

Every alert enters a review queue. No alert triggers automated clinical action. The queue is stored in `alert_history` with `outcome = 'pending'`.

### 7.2 Feedback Processing

```python
async def process_feedback(self, alert_id, outcome, feedback=None):
    """Clinician feedback closes the loop."""
    
    # Update alert
    await self.memory.update_alert_outcome(alert_id, outcome, feedback)
    
    # Update episode
    await self.memory.update_episode_outcome(alert_id, outcome, feedback)
    
    alert = await self.memory.get_alert(alert_id)
    
    # Pattern 9: Learning — calibrate confidence threshold
    if outcome == "dismissed":
        current = await self.memory.get_skill_state(
            alert.skill_name, "confidence_threshold"
        ) or 0.6
        new_threshold = min(0.95, current + 0.05)
        await self.memory.set_skill_state(
            alert.skill_name, "confidence_threshold", new_threshold
        )
        self.events.emit("skill.calibrated", {
            "skill": alert.skill_name, "reason": "false_positive",
            "old": current, "new": new_threshold,
        })
    
    elif outcome == "confirmed":
        await self.memory.set_skill_state(
            alert.skill_name, "last_confirmed", datetime.utcnow().isoformat()
        )
    
    self.events.emit("alert.reviewed", {
        "alert_id": alert_id, "outcome": outcome, "feedback": feedback
    })
```

---

## 8. Guardrails and Safety (Pattern 18)

### 8.1 Guardrail Pipeline

```python
async def _apply_guardrails(self, alerts, ctx):
    filtered = []
    for alert in alerts:
        # Gate 1: Confidence threshold (calibrated by feedback)
        threshold = await self.memory.get_skill_state(
            alert.skill_name, "confidence_threshold"
        ) or 0.6
        if alert.ai_generated and (alert.ai_confidence or 0) < threshold:
            self.events.emit("alert.gated", {"reason": "below_confidence", "alert": alert.title})
            continue
        
        # Gate 2: Hallucination detection
        if alert.ai_generated and alert.evidence:
            if not self._evidence_exists_in_data(alert.evidence, ctx.data):
                self.events.emit("alert.gated", {"reason": "hallucinated_evidence"})
                continue
        
        # Gate 3: Rate limiting
        if alert.severity == "critical":
            recent = await self.memory.count_recent_alerts(
                alert.skill_name, severity="critical", window_hours=1
            )
            if recent >= self.config.max_critical_per_hour:
                self.events.emit("alert.gated", {"reason": "rate_limited"})
                continue
        
        # Invariant: always requires review
        alert.requires_review = True
        
        filtered.append(alert)
    return filtered
```

### 8.2 Safety Invariants

1. **No automated clinical action.** `requires_review = True` on every alert. Non-negotiable.
2. **AI provenance tagging.** Every LLM-involved alert carries `ai_generated`, `ai_model`, `ai_confidence`, `reflection_iterations`.
3. **Hallucination detection.** Evidence cited in findings is cross-referenced against actual fetched data.
4. **Confidence gating.** Findings below calibrated threshold are filtered. Threshold increases with false positives.
5. **Patient data isolation.** Cloud LLMs never see patient identifiers. Only local Ollama may use `allow_patient_data: true`.
6. **Rate limiting.** Max critical alerts per hour per skill prevents alert storms from LLM drift.
7. **Full audit trail.** Every alert, outcome, feedback, and calibration event is persisted and logged.

---

## 9. Resource-Aware Optimization (Pattern 16)

### 9.1 Hardware Profiles

| Profile | RAM | LLM | Concurrent Skills | Max Reflections | Model |
|---------|-----|-----|-------------------|-----------------|-------|
| `pi4_4gb` | 4GB | No | 4 | 0 | None (rules only) |
| `pi4_8gb` | 8GB | Yes | 2 | 2 | phi3:mini |
| `uconsole_8gb` | 8GB | Yes | 2 | 2 | phi3:mini |
| `hub_16gb` | 16GB | Yes | 4 | 3 | llama3.2:3b |
| `hub_32gb` | 32GB | Yes | 8 | 3 | llama3.2:8b |

### 9.2 LLM Slot Management

On Pi 4: one LLM inference at a time. A semaphore gates access. Skills queue by priority. Non-urgent skills can be deferred to the next wake cycle.

---

## 10. Prioritization (Pattern 20)

```python
class Priority(IntEnum):
    CRITICAL = 4   # Ebola, cholera in non-endemic area
    HIGH = 3       # Outbreak thresholds, critical stockouts
    MEDIUM = 2     # Trend anomalies, medication interactions
    LOW = 1        # Routine surveillance, immunisation gap checks
```

Skill execution order: CRITICAL first. Alert emission routing: CRITICAL → SMS + webhook. HIGH → webhook. MEDIUM → FHIR Flag only. LOW → file log.

---

## 11. Exception Handling (Pattern 12)

| Failure | Recovery |
|---------|----------|
| **LLM unavailable** | Entire agent runs in degraded mode (rule fallback for all skills). LLM health checked every 30s. |
| **LLM timeout** | Kill inference after configurable timeout (default 60s). Fall back to rules for that skill. Other skills continue. |
| **LLM OOM** | Ollama process crash detected. Agent emits `llm.crashed` event. Switches to degraded mode. Ollama restarts via sidecar watchdog. |
| **DataAdapter query fails** | Retry with exponential backoff (1s, 2s, 4s, max 3 attempts). If all retries fail, skip that data requirement. Skill runs with partial data (findings will note missing data). |
| **AlertOutput fails** | Alert queued in `emission_queue`. Retried with exponential backoff (30s, 60s, 120s, max 10 attempts). Pending emissions processed on every wake cycle. |
| **Skill throws exception** | Caught and logged. Other skills continue. `skill.error` event emitted. Skill is not disabled — will run again on next trigger. |
| **SQLite locked** | Retry with backoff (100ms, 200ms, 400ms, max 5 attempts). WAL mode reduces contention. |

---

## 12. Hook System

```python
class HookRegistry:
    async def run(self, hook_name, *args):
        for handler in self._hooks.get(hook_name, []):
            await handler(*args)
    
    def register(self, hook_name, handler):
        self._hooks.setdefault(hook_name, []).append(handler)
```

**Available hooks:**

| Hook | When | Arguments |
|------|------|-----------|
| `before_data_fetch` | Before fetching data for a skill | skill |
| `after_data_fetch` | After data fetched | skill, data |
| `before_skill_run` | Before LLM analysis | skill, ctx |
| `after_skill_run` | After analysis complete | skill, alerts |
| `before_alert_emit` | Before sending alerts to outputs | alerts |
| `after_alert_emit` | After alerts sent | alerts |
| `before_llm_prompt` | Before LLM call | skill, system_prompt, prompt |
| `after_llm_response` | After LLM response | skill, response |
| `on_reflection` | Each reflection iteration | skill, iteration, critique |
| `on_degraded_mode` | Skill entering rule fallback | skill, reason |
| `on_feedback` | Clinician feedback received | alert, outcome, feedback |

---

## 13. SKILL.md Format

```yaml
---
name: idsr-cholera
display_name: WHO IDSR Cholera Threshold
description: >
  Detects cholera outbreaks using WHO IDSR thresholds.
version: 1.0.0
author: Dr Akanimoh Osutuk
category: epidemic
priority: critical
region_tags: [global, sub-saharan-africa]

requires:
  resources: [Condition]
  llm: true
  adapter_features: [aggregate]
  min_data_window: 12w

trigger: both
schedule: "0 6 * * 1"
event_filter:
  resource_type: Condition
  code_prefix: "A00"

goal: "Detect cholera outbreaks within 24 hours of first case"
success_criteria:
  detection_window_hours: 24
  target_false_positive_rate: 0.1

max_reflections: 2
confidence_threshold: 0.7

metadata:
  icd10_codes: [A00, A00.0, A00.1, A00.9]
  who_reference: "IDSR Technical Guidelines, 3rd Edition"
  evidence_level: WHO-recommended
---

## Clinical Background

Cholera (ICD-10: A00) is an acute diarrhoeal infection caused by
Vibrio cholerae. The WHO IDSR framework defines:

- Non-endemic area: 1 or more confirmed cases = immediate alert
- Endemic area: Unusual increase above 2× baseline = alert

## Reasoning Instructions

Given cholera case data grouped by site and week, you should:

1. Check for any sites with NEW cases where baseline is zero (non-endemic threshold)
2. Check for sites where this week exceeds 2× the weekly baseline (endemic threshold)
3. Look at broader diarrhoeal disease data for unconfirmed cholera signals
4. Consider spatial patterns — are neighbouring sites showing similar trends?
5. For each finding, explain what a site medical officer should do next

Always state your confidence as a number between 0.0 and 1.0.
Always cite specific data points from the tables provided.

## Rule-Based Fallback

When LLM is unavailable:
- count(this_week) >= 1 AND baseline == 0 → severity: critical
- count(this_week) > 2 × baseline → severity: high
```

---

## 14. Example Skill: IDSR Cholera (Full Implementation)

```python
class IdsrCholeraSkill(Skill):
    
    def name(self): return "idsr-cholera"
    def trigger(self): return SkillTrigger.BOTH
    def schedule(self): return "0 6 * * 1"
    def priority(self): return Priority.CRITICAL
    
    def event_filter(self):
        return {"resource_type": "Condition", "code_prefix": "A00"}
    
    def goal(self):
        return "Detect cholera outbreaks within 24 hours of first case"
    
    def required_data(self):
        return {
            "cholera_12w": DataRequirement(
                resource_type="Condition",
                filters={"code": ["A00", "A00.0", "A00.1", "A00.9"],
                          "clinical_status": "active"},
                time_window="12w",
                group_by=["site_id", "week"],
                metric="count",
                name="cholera_12w",
            ),
            "cholera_this_week": DataRequirement(
                resource_type="Condition",
                filters={"code": ["A00", "A00.0", "A00.1", "A00.9"],
                          "clinical_status": "active"},
                time_window="1w",
                group_by=["site_id"],
                metric="count",
                name="cholera_this_week",
            ),
            "diarrhoeal_4w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A0"},
                time_window="4w",
                group_by=["site_id", "week"],
                metric="count",
                name="diarrhoeal_4w",
            ),
        }
    
    def build_prompt(self, ctx):
        prompt = "## Cholera Surveillance Data\n\n"
        prompt += "### Confirmed cholera cases (12 weeks, by site and week):\n"
        prompt += self._format_table(ctx.data["cholera_12w"])
        prompt += "\n### This week's cholera cases (by site):\n"
        prompt += self._format_table(ctx.data["cholera_this_week"])
        prompt += "\n### All diarrhoeal diseases (4 weeks, by site):\n"
        prompt += self._format_table(ctx.data["diarrhoeal_4w"])
        
        if ctx.baselines:
            prompt += "\n### Learned baselines:\n"
            for metric, val in ctx.baselines.items():
                prompt += f"- {metric}: {val:.1f}\n"
        
        prompt += (
            "\n## Task\n"
            "Analyze using WHO IDSR cholera thresholds:\n"
            "1. Sites with NEW cases where 12-week baseline is zero (≥1 = critical)\n"
            "2. Sites where this week >2× weekly baseline (= high)\n"
            "3. Diarrhoeal disease patterns that might indicate unconfirmed cholera\n"
            "4. Spatial patterns between neighbouring sites\n"
            "5. For each finding: what should the site medical officer do?\n"
        )
        return prompt
    
    def response_schema(self):
        return {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string",
                                "enum": ["critical", "high", "moderate", "low"]},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "reasoning": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "site_id": {"type": "string"},
                            "measured_value": {"type": "number"},
                            "threshold_value": {"type": "number"},
                            "recommended_action": {"type": "string"},
                            "dedup_key": {"type": "string"},
                        }
                    }
                },
                "summary": {"type": "string"},
            }
        }
    
    def critique_findings(self, findings, ctx):
        """Validate LLM findings against actual data. Return ACCEPT or critique."""
        issues = []
        this_week = {r["site_id"]: r["count"] for r in ctx.data["cholera_this_week"]}
        
        for f in findings:
            site = f.get("site_id")
            if not site:
                issues.append(f"Finding '{f.get('title','')}' has no site_id.")
                continue
            actual = this_week.get(site, 0)
            claimed = f.get("measured_value", 0)
            if actual == 0 and claimed > 0:
                issues.append(
                    f"Finding claims {claimed} cases at {site}, "
                    f"but actual data shows 0. This appears hallucinated."
                )
            elif abs(actual - claimed) > 1:
                issues.append(
                    f"Finding claims {claimed} cases at {site}, "
                    f"but actual is {actual}. Please correct."
                )
        
        if not issues:
            return "ACCEPT"
        
        return "ISSUES FOUND:\n" + "\n".join(f"- {i}" for i in issues)
    
    def rule_fallback(self, ctx):
        alerts = []
        this_week = ctx.data.get("cholera_this_week", [])
        historical = ctx.data.get("cholera_12w", [])
        
        for row in this_week:
            site_id = row["site_id"]
            count = row["count"]
            if count == 0:
                continue
            
            baseline = self._compute_baseline(historical, site_id)
            
            if baseline == 0 and count >= 1:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="outbreak",
                    title=f"Cholera: {count} case(s) at {site_id} — non-endemic",
                    description=f"{count} cholera case(s) this week. No cases in prior 12 weeks.",
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline},
                    threshold="WHO IDSR: ≥1 case in non-endemic area",
                    measured_value=count,
                    threshold_value=1,
                    dedup_key=f"idsr-cholera-{site_id}-{self._current_epiweek()}",
                ))
            elif count > baseline * 2:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="outbreak",
                    title=f"Cholera: unusual increase at {site_id}",
                    description=f"{count} cases. Baseline: {baseline:.1f}/week. Exceeds 2× threshold.",
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline},
                    measured_value=count,
                    threshold_value=baseline * 2,
                    dedup_key=f"idsr-cholera-{site_id}-{self._current_epiweek()}",
                ))
        
        return alerts
```

---

## 15. Skill Testing Harness

```python
from open_sentinel.testing import SkillTestHarness, MockLLMEngine

def test_cholera_llm_with_reflection():
    """Test: LLM finds outbreak, reflection validates, alert emitted."""
    harness = SkillTestHarness(
        IdsrCholeraSkill(),
        llm=MockLLMEngine(responses=[
            # First inference: LLM finds outbreak
            {"findings": [{
                "severity": "critical",
                "title": "Cholera at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 3,
                "confidence": 0.92,
                "reasoning": "3 confirmed cases, zero baseline.",
            }]},
        ])
    )
    harness.set_data("cholera_12w", [])
    harness.set_data("cholera_this_week", [{"site_id": "clinic-01", "count": 3}])
    harness.set_data("diarrhoeal_4w", [])
    
    result = harness.run()
    assert result.alerts_count == 1
    assert result.alerts[0].severity == "critical"
    assert result.alerts[0].ai_generated == True
    assert result.reflection_count == 0  # Passed first critique


def test_cholera_hallucination_caught():
    """Test: LLM hallucinates cases, reflection catches it."""
    harness = SkillTestHarness(
        IdsrCholeraSkill(),
        llm=MockLLMEngine(responses=[
            # First inference: LLM hallucinates 5 cases at clinic-02
            {"findings": [{
                "severity": "critical",
                "title": "Cholera at clinic-02",
                "site_id": "clinic-02",
                "measured_value": 5,
                "confidence": 0.85,
            }]},
            # Second inference (after reflection): LLM corrects
            {"findings": []},
        ])
    )
    harness.set_data("cholera_12w", [])
    harness.set_data("cholera_this_week", [{"site_id": "clinic-02", "count": 0}])
    harness.set_data("diarrhoeal_4w", [])
    
    result = harness.run()
    assert result.alerts_count == 0  # Hallucination caught
    assert result.reflection_count == 1


def test_cholera_degraded_mode():
    """Test: No LLM, rules still catch the outbreak."""
    harness = SkillTestHarness(
        IdsrCholeraSkill(),
        llm=None,
    )
    harness.set_data("cholera_12w", [])
    harness.set_data("cholera_this_week", [{"site_id": "clinic-01", "count": 3}])
    harness.set_data("diarrhoeal_4w", [])
    
    result = harness.run()
    assert result.alerts_count == 1
    assert result.alerts[0].ai_generated == False
    assert result.alerts[0].severity == "critical"
```

---

## 16. Skill Registry and Community (SentinelHub)

### 16.1 CLI

```bash
sentinel install malaria-west-africa        # Install community skill
sentinel update --all                        # Update all skills
sentinel search --category epidemic --region sub-saharan-africa
sentinel publish ./my-skill/                 # Publish to SentinelHub
sentinel test ./my-skill/                    # Run skill test harness
```

### 16.2 Skill Locations and Precedence

```
1. Built-in skills     (shipped with open-sentinel pip package)    lowest
2. Community skills     (~/.sentinel/skills/)                      middle
3. Deployment skills    (<config_dir>/skills/)                     highest
```

### 16.3 Skill Gating

Skills filtered at load time by their `requires` metadata. Missing LLM → skill loads but runs degraded. Missing adapter features → skill skipped. Missing resource types → skill skipped. Insufficient data window → skill loads with warning.

---

## 17. Complete Skill Set

| Skill | Priority | Category | LLM Enhancement |
|-------|----------|----------|-----------------|
| `idsr-cholera` | CRITICAL | epidemic | Spatial patterns, unconfirmed case detection |
| `idsr-measles` | CRITICAL | epidemic | Vaccination coverage correlation |
| `idsr-meningitis` | CRITICAL | epidemic | Meningitis belt seasonal adjustment |
| `idsr-yellow-fever` | CRITICAL | epidemic | Travel history cross-referencing |
| `idsr-ebola` | CRITICAL | epidemic | Contact tracing pattern detection |
| `malaria-trend` | HIGH | epidemic | Seasonal anomaly with climate correlation |
| `medication-missed-dose` | HIGH | medication-safety | Adherence pattern reasoning |
| `medication-interaction-retro` | HIGH | medication-safety | Multi-drug interaction chains |
| `stockout-prediction` | MEDIUM | stockout | Consumption trend forecasting |
| `stockout-critical` | HIGH | stockout | Redistribution recommendation |
| `immunisation-gap` | MEDIUM | immunisation | Catch-up schedule generation |
| `tb-treatment-completion` | MEDIUM | treatment | Abandonment risk scoring |
| `maternal-risk-scoring` | HIGH | maternal | Multi-factor risk synthesis |
| `missed-referral` | MEDIUM | referral | Urgency assessment from clinical context |
| `vital-sign-trend` | HIGH | clinical | Deterioration trajectory prediction |
| `syndromic-surveillance` | HIGH | syndromic | Multi-signal cross-correlation (LLM-only) |

---

## 18. Lifecycle Events (Pattern 19)

| Event | Payload |
|-------|---------|
| `agent.started` | agent_id, skills_loaded, hardware_profile |
| `agent.wake` | trigger_type, event_summary |
| `agent.sleep` | next_wake_time |
| `agent.error` | error |
| `skill.started` | run_id, skill, priority |
| `skill.reflecting` | run_id, iteration, critique_summary |
| `skill.degraded` | run_id, skill, reason |
| `skill.deferred` | skill, reason |
| `skill.completed` | run_id, skill, alerts, reflections, tokens, duration_ms, degraded |
| `skill.error` | run_id, skill, error |
| `skill.calibrated` | skill, reason, old_threshold, new_threshold |
| `skill.tool_use_error` | run_id, error |
| `llm.inference.started` | run_id, model |
| `llm.inference.completed` | run_id, duration_ms, tokens |
| `llm.crashed` | error |
| `alert.emitted` | alert_id, severity, output |
| `alert.gated` | reason, alert_title |
| `alert.deduplicated` | dedup_key |
| `alert.reviewed` | alert_id, outcome, feedback |
| `data.fetch.completed` | skill, resource_type, records, duration_ms |
| `memory.episode.stored` | skill, site_id |
| `resource.llm_slot.acquired` | queue_depth |
| `resource.llm_slot.released` | — |

---

## 19. Repository Structure

```
open-sentinel/
├── README.md
├── LICENSE
├── CLAUDE.md
├── CONTRIBUTING.md
├── pyproject.toml
│
├── open_sentinel/
│   ├── __init__.py
│   ├── agent.py              # SentinelAgent: sleeper loop, event handling, skill execution
│   ├── interfaces.py         # ABC: DataAdapter, Skill, AlertOutput, LLMEngine
│   ├── types.py              # Alert, DataEvent, DataRequirement, AnalysisContext, Episode, etc.
│   ├── registry.py           # SkillRegistry: SKILL.md parsing, gating, event matching
│   ├── memory.py             # MemoryStore: working, episodic, semantic, procedural (SQLite)
│   ├── reflection.py         # Reflection loop engine
│   ├── guardrails.py         # Safety pipeline: confidence, hallucination, rate limit
│   ├── priority.py           # PriorityQueue: skill ranking, alert ranking
│   ├── resources.py          # ResourceManager: hardware profiles, LLM slot semaphore
│   ├── feedback.py           # HITL: feedback processing, skill calibration
│   ├── scheduler.py          # Cron-based skill scheduling
│   ├── dedup.py              # Deduplication by dedup_key + time window
│   ├── hooks.py              # HookRegistry: before/after extension points
│   ├── events.py             # EventBus: lifecycle event emission + subscription
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── fhir_git.py       # Open Nucleus FHIR Git + SQLite index
│   │   ├── fhir_http.py      # Any FHIR R4 server
│   │   ├── dhis2.py          # DHIS2 Web API
│   │   ├── openmrs.py        # OpenMRS REST API
│   │   ├── sqlite_adapter.py # Generic SQLite database
│   │   └── csv_adapter.py    # CSV/TSV file directory
│   │
│   ├── outputs/
│   │   ├── __init__.py
│   │   ├── fhir_flag.py      # Write FHIR DetectedIssue/Flag
│   │   ├── fhir_http.py      # POST to any FHIR server
│   │   ├── dhis2_event.py    # DHIS2 tracked entity event
│   │   ├── webhook.py        # Generic HTTP webhook
│   │   ├── sms.py            # Africa's Talking / Twilio
│   │   ├── email_output.py   # SMTP
│   │   ├── file_output.py    # JSON lines file
│   │   └── console.py        # Stdout (development)
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── ollama.py         # Primary: local Ollama
│   │   ├── openai_engine.py  # OpenAI API (anonymised data only)
│   │   ├── anthropic_engine.py
│   │   └── mock.py           # Testing
│   │
│   └── testing/
│       ├── __init__.py
│       ├── harness.py        # SkillTestHarness
│       ├── mock_llm.py       # MockLLMEngine with sequenced responses
│       └── fixtures.py       # FHIR test data generators
│
├── skills/                   # Built-in skills (16 folders)
│   ├── idsr-cholera/
│   │   ├── SKILL.md
│   │   └── skill.py
│   ├── idsr-measles/
│   ├── idsr-meningitis/
│   ├── idsr-yellow-fever/
│   ├── idsr-ebola/
│   ├── malaria-trend/
│   ├── medication-missed-dose/
│   ├── medication-interaction-retro/
│   ├── stockout-prediction/
│   ├── stockout-critical/
│   ├── immunisation-gap/
│   ├── tb-treatment-completion/
│   ├── maternal-risk-scoring/
│   ├── missed-referral/
│   ├── vital-sign-trend/
│   └── syndromic-surveillance/
│
├── tests/
├── examples/
└── docs/
```

---

## 20. Build Plan

### Phase 1: Core Framework (Week 1-3)
Interfaces (`DataAdapter`, `Skill`, `AlertOutput`, `LLMEngine`, `MemoryStore`). Agent loop with sleeper, event routing, prioritization, parallelization. OllamaEngine + MockEngine. SKILL.md parser with gating. Three-tier memory (SQLite). Reflection loop. Guardrail pipeline. Resource manager. Event bus + hooks. Skill testing harness.

### Phase 2: First Skills + Adapters (Week 4-5)
`FhirGitAdapter`, `SqliteAdapter`, `CsvAdapter`. Five IDSR skills (cholera, measles, meningitis, yellow fever, ebola). Both LLM and rule paths. Episodic memory integration. `ConsoleOutput`, `FileOutput`, `WebhookOutput`.

### Phase 3: Clinical + Supply Skills + HITL (Week 6-7)
Medication safety (2 skills), stockout (2), immunisation, TB, maternal risk, vital signs. `SmsOutput`, `FhirFlagOutput`. Feedback processing with skill calibration. Exception handling for all failure modes.

### Phase 4: Syndromic + Community (Week 8-9)
Syndromic surveillance (planning pattern, LLM-only). SentinelHub registry. Skill contribution guide + templates. `Dhis2Adapter`, `OpenMrsAdapter`, `FhirHttpAdapter`.

### Phase 5: Documentation + Evaluation (Week 10)
GitHub Pages documentation. Evaluation framework (precision/recall tracking). Community outreach (WHO AFRO, DHIS2 community, OpenMRS implementers). Example deployment guide for Pi 4 + Open Nucleus.

---

## 21. Performance Targets

Raspberry Pi 4 (8GB, Ollama + phi3:mini).

| Operation | Target |
|-----------|--------|
| Agent startup | < 3s |
| Event → skill dispatch | < 10ms |
| Data fetch (1K resources) | < 500ms |
| LLM inference (single) | < 30s |
| Reflection iteration | < 25s |
| Full skill (LLM + 2 reflections) | < 90s |
| Rule fallback (single skill) | < 100ms |
| Full sweep, 16 skills, LLM | < 5 minutes |
| Full sweep, rules only | < 5s |
| Alert emission (webhook) | < 200ms |
| Memory query (episodes) | < 10ms |
| Agent RSS (no LLM active) | < 60MB |
| Ollama RSS (inferring) | < 4GB |

---

## 22. Security

1. **Patient data isolation.** Cloud LLMs never receive patient identifiers. Local Ollama: `allow_patient_data: true`. Cloud: aggregated, anonymised data only.
2. **No automated clinical action.** `requires_review = True` on every alert. Non-negotiable. The agent recommends. The clinician decides.
3. **Hallucination detection.** LLM findings are validated against actual data via `critique_findings()` (reflection) and `_evidence_exists_in_data()` (guardrails).
4. **Confidence gating.** Calibrated threshold (default 0.6, raised by false positive feedback). Findings below threshold are filtered.
5. **AI provenance.** Every alert: `ai_generated`, `ai_model`, `ai_confidence`, `reflection_iterations`, `rule_validated`.
6. **Rate limiting.** Configurable max critical alerts per hour per skill.
7. **Audit trail.** Every alert, outcome, feedback, calibration, and exception event is persisted with timestamps.
8. **Episodic learning safety.** False positive feedback raises the confidence threshold — the agent becomes more cautious, not less. Threshold has a ceiling (0.95) to prevent skills from being gated into silence.

---

*open-sentinel • FibrinLab*  
*Built on 21 agentic design patterns.*  
*Because an outbreak shouldn't wait for a dashboard refresh.*  
*And a rule shouldn't be the smartest thing watching your data.*
