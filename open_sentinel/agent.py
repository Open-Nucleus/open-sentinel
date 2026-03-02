"""SentinelAgent: the core agent loop that wires everything together."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from open_sentinel.dedup import Deduplicator
from open_sentinel.events import EventBus
from open_sentinel.feedback import FeedbackProcessor
from open_sentinel.guardrails import GuardrailPipeline
from open_sentinel.hooks import HookRegistry
from open_sentinel.interfaces import AlertOutput, DataAdapter, LLMEngine, Skill
from open_sentinel.memory import SqliteMemoryStore
from open_sentinel.priority import PriorityQueue
from open_sentinel.reflection import ReflectionEngine, _parse_structured
from open_sentinel.registry import SkillRegistry
from open_sentinel.resources import ResourceManager
from open_sentinel.scheduler import Scheduler
from open_sentinel.types import (
    AgentConfig,
    Alert,
    AnalysisContext,
    DataEvent,
    DataRequirement,
    Episode,
)

logger = logging.getLogger(__name__)

_SYSTEM_PREAMBLE = (
    "You are a clinical surveillance analyst running on an offline health data system "
    "deployed in resource-limited settings. Your role is to analyze clinical data and "
    "identify potential public health threats, medication safety issues, and supply chain "
    "problems. Be precise, evidence-based, and conservative in your assessments. "
    "Every finding must reference actual data you were given."
)


class SentinelAgent:
    def __init__(
        self,
        data_adapter: DataAdapter,
        llm: LLMEngine,
        skills: List[Skill],
        outputs: List[AlertOutput],
        config: Optional[AgentConfig] = None,
    ):
        self.data = data_adapter
        self.llm = llm
        self.config = config or AgentConfig()
        self.memory = SqliteMemoryStore(self.config.state_db_path)
        self.skill_registry = SkillRegistry(skills)
        self.outputs = outputs
        self.events = EventBus()
        self.hooks = HookRegistry()
        self.scheduler = Scheduler()
        self.priority_queue = PriorityQueue()
        self.resource_manager = ResourceManager(self.config.hardware)
        self._guardrails = GuardrailPipeline(
            self.memory, self.events, self.config.max_critical_per_hour
        )
        self._reflection = ReflectionEngine(self.resource_manager, self.events)
        self._dedup = Deduplicator(self.memory)
        self._feedback = FeedbackProcessor(self.memory, self.events)
        self._running = False

    async def start(self) -> None:
        await self.memory.initialize()
        self.events.emit(
            "agent.started",
            agent_id=str(uuid4()),
            skills_loaded=[s.name() for s in self.skill_registry.all_skills()],
            hardware_profile=self.config.hardware,
        )

    async def stop(self) -> None:
        self._running = False
        await self.scheduler.stop()
        await self.memory.close()

    async def run(self) -> None:
        """Main sleeper loop. Registers schedules, subscribes to events."""
        self._running = True

        # Register scheduled skills
        for skill in self.skill_registry.all_skills():
            sched = skill.schedule()
            if sched:
                self.scheduler.register(
                    skill.name(),
                    sched,
                    self._handle_scheduled_skill,
                )
        await self.scheduler.start()

        # Subscribe to data events
        event_types = self.skill_registry.all_event_types()
        async for event in self.data.subscribe(event_types):
            if not self._running:
                break
            self.events.emit("agent.wake", trigger_type="event", event_summary=event.event_type)
            try:
                await self._handle_event(event)
            except Exception:
                logger.exception("Error handling event")
                self.events.emit("agent.error", error="event handling failed")
            await self._process_emission_queue()
            self.events.emit(
                "agent.sleep",
                next_wake_time=str(self.scheduler.next_wake_time()),
            )

    async def _handle_scheduled_skill(self, skill_name: str) -> None:
        skill = self.skill_registry.get(skill_name)
        if not skill:
            return
        event = DataEvent(
            event_type="schedule.triggered",
            resource_type="",
            metadata={"skill": skill_name},
        )
        self.events.emit("agent.wake", trigger_type="schedule", event_summary=skill_name)
        llm_available = await self.llm.available()
        if llm_available and self.resource_manager.llm_enabled():
            await self.resource_manager.acquire_llm_slot()
            try:
                await self._run_skill(skill, event)
            finally:
                self.resource_manager.release_llm_slot()
        else:
            await self._run_rule_path(skill, event)

    async def _handle_event(self, event: DataEvent) -> None:
        matched = self.skill_registry.match_event(event)
        if not matched:
            return

        ranked = self.priority_queue.rank_skills(matched)
        llm_available = await self.llm.available()

        if not llm_available or not self.resource_manager.llm_enabled():
            # Degraded mode: run all in parallel via rule path
            tasks = [self._run_rule_path(skill, event) for skill in ranked]
            await asyncio.gather(*tasks, return_exceptions=True)
            return

        # LLM available: run sequentially through priority queue
        for skill in ranked:
            await self.resource_manager.acquire_llm_slot()
            try:
                await self._run_skill(skill, event)
            except Exception:
                logger.exception("Skill %s failed", skill.name())
                self.events.emit("skill.error", skill=skill.name(), error="skill execution failed")
            finally:
                self.resource_manager.release_llm_slot()

    async def _run_skill(self, skill: Skill, event: DataEvent) -> List[Alert]:
        """Full LLM pipeline for a single skill."""
        run_id = str(uuid4())
        skill_name = skill.name()
        start_time = time.monotonic()
        total_tokens = 0

        self.events.emit(
            "skill.started",
            run_id=run_id,
            skill=skill_name,
            priority=skill.priority().name,
        )

        # 1. Fetch data
        await self.hooks.run("before_data_fetch", skill)
        data = await self._fetch_all_data(skill, event)
        await self.hooks.run("after_data_fetch", skill, data)

        # 2. Load memory
        site_id = event.site_id or ""
        episodes = await self.memory.recall_episodes(skill_name, site_id)
        baselines: Dict[str, float] = {}
        for req_name, req in skill.required_data().items():
            if req.metric:
                val = await self.memory.get_baseline(skill_name, site_id, req_name)
                if val is not None:
                    baselines[req_name] = val

        previous_alerts = await self.memory.recent_alerts(skill_name, limit=10)

        # 3. Build context
        ctx = AnalysisContext(
            trigger="event" if event.event_type != "schedule.triggered" else "schedule",
            trigger_event=event,
            data=data,
            site_id=site_id or None,
            config=self.config.skill_config.get(skill_name, {}),
            llm=self.llm,
            memory=self.memory,
            episodes=episodes,
            baselines=baselines,
            previous_alerts=previous_alerts,
        )

        # 4. Build prompt + reason
        await self.hooks.run("before_skill_run", skill, ctx)
        prompt = skill.build_prompt(ctx)
        schema = skill.response_schema()

        skill_md = self.skill_registry.get_skill_md(skill_name)
        system_prompt = self._build_system_prompt(skill_md, episodes)

        await self.hooks.run("before_llm_prompt", skill, system_prompt, prompt)
        self.events.emit("llm.inference.started", run_id=run_id, model=self.llm.model())

        response = await self.llm.reason(system_prompt, prompt, skill.goal() or "Analyze", schema)
        total_tokens += response.tokens_used

        self.events.emit(
            "llm.inference.completed",
            run_id=run_id,
            duration_ms=response.duration_ms,
            tokens=response.tokens_used,
        )
        await self.hooks.run("after_llm_response", skill, response)

        findings = _parse_structured(response.text)

        # 5. Reflection loop
        findings, reflection_count = await self._reflection.run_reflection_loop(
            findings, skill, ctx, self.llm, prompt, schema, run_id
        )

        # 6. Tool use (additional data requests)
        if skill.can_request_additional_data():
            for finding in findings:
                if "additional_data_needed" in finding:
                    try:
                        extra_req = skill.handle_additional_data_request(
                            finding["additional_data_needed"]
                        )
                        extra_data = await self._fetch_data(extra_req, event)
                        data[extra_req.name or "additional"] = extra_data
                        ctx = ctx.model_copy(update={"data": data})
                    except Exception:
                        logger.exception("Tool use error in %s", skill_name)
                        self.events.emit(
                            "skill.tool_use_error",
                            run_id=run_id,
                            error="additional data fetch failed",
                        )

        # 7. Convert findings to alerts + guardrails
        alerts = self._findings_to_alerts(
            findings, skill_name, event, response, reflection_count
        )
        alerts = await self._guardrails.apply(alerts, ctx, skill_name)

        # 8. Deduplicate
        alerts = await self._dedup.deduplicate(alerts)

        # 9. Prioritize and emit
        alerts = self.priority_queue.rank_alerts(alerts)
        await self.hooks.run("before_alert_emit", alerts)
        for alert in alerts:
            await self._emit_alert(alert)
        await self.hooks.run("after_alert_emit", alerts)
        await self.hooks.run("after_skill_run", skill, alerts)

        # 10. Store episode
        duration_ms = int((time.monotonic() - start_time) * 1000)
        episode = Episode(
            skill_name=skill_name,
            site_id=site_id or None,
            trigger=ctx.trigger,
            findings_summary=json.dumps(findings)[:500],
            alerts_generated=len(alerts),
            related_alert_ids=[a.id for a in alerts],
        )
        await self.memory.store_episode(episode)
        self.events.emit("memory.episode.stored", skill=skill_name, site_id=site_id)

        self.events.emit(
            "skill.completed",
            run_id=run_id,
            skill=skill_name,
            alerts=len(alerts),
            reflections=reflection_count,
            tokens=total_tokens,
            duration_ms=duration_ms,
            degraded=False,
        )

        return alerts

    async def _run_rule_path(self, skill: Skill, event: DataEvent) -> List[Alert]:
        """Degraded mode: rule-based fallback only."""
        run_id = str(uuid4())
        skill_name = skill.name()

        self.events.emit(
            "skill.degraded",
            run_id=run_id,
            skill=skill_name,
            reason="llm_unavailable",
        )
        await self.hooks.run("on_degraded_mode", skill, "llm_unavailable")

        data = await self._fetch_all_data(skill, event)
        site_id = event.site_id or ""

        ctx = AnalysisContext(
            trigger="event",
            trigger_event=event,
            data=data,
            site_id=site_id or None,
            config=self.config.skill_config.get(skill_name, {}),
            llm=self.llm,
            memory=self.memory,
            episodes=[],
            baselines={},
            previous_alerts=[],
        )

        alerts = skill.rule_fallback(ctx)

        # Tag all alerts as non-AI
        tagged: List[Alert] = []
        for alert in alerts:
            alert = alert.model_copy(update={
                "ai_generated": False,
                "ai_reasoning": "[LLM unavailable — rule-based detection only]",
                "rule_validated": True,
            })
            tagged.append(alert)

        tagged = await self._dedup.deduplicate(tagged)
        for alert in tagged:
            await self._emit_alert(alert)

        self.events.emit(
            "skill.completed",
            run_id=run_id,
            skill=skill_name,
            alerts=len(tagged),
            reflections=0,
            tokens=0,
            duration_ms=0,
            degraded=True,
        )

        return tagged

    def _build_system_prompt(
        self,
        skill_md: Optional[str],
        episodes: List[Episode],
    ) -> str:
        parts = [_SYSTEM_PREAMBLE]

        if skill_md:
            parts.append(f"\n\n## Skill Context\n\n{skill_md}")

        if episodes:
            parts.append("\n\n## Recent Episodes\n")
            for ep in episodes[:3]:
                parts.append(
                    f"- [{ep.timestamp.isoformat()}] {ep.findings_summary} "
                    f"(outcome: {ep.outcome})"
                )
                if ep.clinician_feedback:
                    parts.append(f"  Feedback: {ep.clinician_feedback}")

        return "\n".join(parts)

    def _findings_to_alerts(
        self,
        findings: List[Dict[str, Any]],
        skill_name: str,
        event: DataEvent,
        response: Any,
        reflection_count: int,
    ) -> List[Alert]:
        alerts: List[Alert] = []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            alert = Alert(
                skill_name=skill_name,
                severity=finding.get("severity", "moderate"),
                category=finding.get("category", ""),
                title=finding.get("title", "Untitled finding"),
                description=finding.get("description", ""),
                site_id=event.site_id,
                evidence=finding.get("evidence"),
                measured_value=finding.get("measured_value"),
                threshold_value=finding.get("threshold_value"),
                ai_generated=True,
                ai_confidence=finding.get("confidence") or getattr(response, "confidence", None),
                ai_model=getattr(response, "model", None),
                ai_reasoning=finding.get("reasoning", ""),
                reflection_iterations=reflection_count,
                dedup_key=finding.get("dedup_key"),
            )
            alerts.append(alert)
        return alerts

    async def _emit_alert(self, alert: Alert) -> None:
        await self.memory.store_alert(alert)
        for output in self.outputs:
            if output.accepts(alert):
                try:
                    success = await output.emit(alert)
                    if success:
                        self.events.emit(
                            "alert.emitted",
                            alert_id=alert.id,
                            severity=alert.severity,
                            output=output.name(),
                        )
                    else:
                        await self.memory.queue_emission(
                            alert.id, output.name(), alert.model_dump_json()
                        )
                except Exception:
                    logger.exception("Output %s failed for alert %s", output.name(), alert.id)
                    await self.memory.queue_emission(
                        alert.id, output.name(), alert.model_dump_json()
                    )

    async def _process_emission_queue(self) -> None:
        pending = await self.memory.get_pending_emissions()
        for emission in pending:
            output = next(
                (o for o in self.outputs if o.name() == emission["output_name"]),
                None,
            )
            if not output:
                await self.memory.mark_emission_complete(emission["id"])
                continue

            alert_data = emission["data"]
            try:
                alert = Alert.model_validate_json(alert_data)
                success = await output.emit(alert)
                if success:
                    await self.memory.mark_emission_complete(emission["id"])
                else:
                    attempts = emission["attempts"]
                    delay = min(120, 30 * (2 ** attempts))
                    next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    await self.memory.mark_emission_failed(emission["id"], next_retry)
            except Exception:
                attempts = emission["attempts"]
                delay = min(120, 30 * (2 ** attempts))
                next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay)
                await self.memory.mark_emission_failed(emission["id"], next_retry)

    async def _fetch_all_data(
        self, skill: Skill, event: DataEvent
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for req_name, req in skill.required_data().items():
            try:
                data[req_name] = await self._fetch_data(req, event)
                self.events.emit(
                    "data.fetch.completed",
                    skill=skill.name(),
                    resource_type=req.resource_type,
                    records=len(data[req_name]) if isinstance(data[req_name], list) else 1,
                )
            except Exception:
                logger.exception("Data fetch failed for %s", req_name)
                data[req_name] = []
        return data

    async def _fetch_data(
        self, req: DataRequirement, event: DataEvent
    ) -> Any:
        if req.metric and req.group_by and self.data.supports("aggregate"):
            return await self.data.aggregate(
                req.resource_type, req.group_by, req.metric, req.filters
            )
        return await self.data.query(req.resource_type, req.filters, req.limit)

    async def process_feedback(
        self, alert_id: str, outcome: str, feedback: Optional[str] = None
    ) -> None:
        await self._feedback.process_feedback(alert_id, outcome, feedback)
