"""Tests for SkillRegistry."""

from typing import Dict, List, Optional

from open_sentinel.interfaces import Skill
from open_sentinel.registry import SkillRegistry
from open_sentinel.types import (
    Alert,
    AnalysisContext,
    DataEvent,
    DataRequirement,
    Priority,
    SkillTrigger,
)


class _TestSkill(Skill):
    def __init__(
        self,
        skill_name: str,
        skill_priority: Priority = Priority.MEDIUM,
        skill_trigger: SkillTrigger = SkillTrigger.EVENT,
        resource_types: Optional[List[str]] = None,
        skill_event_filter: Optional[Dict] = None,
    ):
        self._name = skill_name
        self._priority = skill_priority
        self._trigger = skill_trigger
        self._resource_types = resource_types or ["Condition"]
        self._event_filter = skill_event_filter

    def name(self) -> str:
        return self._name

    def priority(self) -> Priority:
        return self._priority

    def trigger(self) -> SkillTrigger:
        return self._trigger

    def event_filter(self) -> Optional[Dict]:
        return self._event_filter

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            rt: DataRequirement(resource_type=rt)
            for rt in self._resource_types
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        return "test prompt"

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        return []


class TestSkillRegistry:
    def test_register_and_get(self):
        reg = SkillRegistry()
        skill = _TestSkill("cholera")
        reg.register(skill)
        assert reg.get("cholera") is skill

    def test_get_missing(self):
        reg = SkillRegistry()
        assert reg.get("nonexistent") is None

    def test_all_skills(self):
        skills = [_TestSkill("a"), _TestSkill("b")]
        reg = SkillRegistry(skills)
        assert len(reg.all_skills()) == 2

    def test_match_event_by_resource_type(self):
        reg = SkillRegistry([
            _TestSkill("cholera", resource_types=["Condition"]),
            _TestSkill("stockout", resource_types=["SupplyDelivery"]),
        ])
        event = DataEvent(event_type="resource.created", resource_type="Condition")
        matched = reg.match_event(event)
        assert len(matched) == 1
        assert matched[0].name() == "cholera"

    def test_match_event_with_filter(self):
        reg = SkillRegistry([
            _TestSkill(
                "cholera",
                skill_event_filter={
                    "resource_type": "Condition",
                    "code_prefix": "A00",
                },
            ),
        ])
        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            resource_data={
                "code": {"coding": [{"code": "A00.1"}]},
            },
        )
        matched = reg.match_event(event)
        assert len(matched) == 1

    def test_no_match_wrong_code_prefix(self):
        reg = SkillRegistry([
            _TestSkill(
                "cholera",
                skill_event_filter={
                    "resource_type": "Condition",
                    "code_prefix": "A00",
                },
            ),
        ])
        event = DataEvent(
            event_type="resource.created",
            resource_type="Condition",
            resource_data={
                "code": {"coding": [{"code": "B99.0"}]},
            },
        )
        matched = reg.match_event(event)
        assert len(matched) == 0

    def test_schedule_only_skill_not_matched_by_event(self):
        reg = SkillRegistry([
            _TestSkill("daily", skill_trigger=SkillTrigger.SCHEDULE),
        ])
        event = DataEvent(event_type="resource.created", resource_type="Condition")
        matched = reg.match_event(event)
        assert len(matched) == 0

    def test_all_event_types(self):
        reg = SkillRegistry([
            _TestSkill("a", resource_types=["Condition", "Observation"]),
            _TestSkill("b", resource_types=["MedicationRequest"]),
        ])
        types = reg.all_event_types()
        assert set(types) == {"Condition", "MedicationRequest", "Observation"}

    def test_init_with_skills(self):
        skills = [_TestSkill("x"), _TestSkill("y")]
        reg = SkillRegistry(skills)
        assert reg.get("x") is not None
        assert reg.get("y") is not None
