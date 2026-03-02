"""Skill registry: registration, SKILL.md parsing, event matching, gating."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import frontmatter

from open_sentinel.interfaces import DataAdapter, Skill
from open_sentinel.resources import ResourceManager
from open_sentinel.types import DataEvent, SkillTrigger

logger = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self, skills: Optional[List[Skill]] = None):
        self._skills: Dict[str, Skill] = {}
        self._skill_md: Dict[str, Dict[str, Any]] = {}
        self._skill_md_content: Dict[str, str] = {}

        if skills:
            for skill in skills:
                self.register(skill)

    def register(
        self,
        skill: Skill,
        skill_md_path: Optional[str] = None,
    ) -> None:
        name = skill.name()
        self._skills[name] = skill
        if skill_md_path:
            self._load_skill_md(name, skill_md_path)

    def _load_skill_md(self, name: str, path: str) -> None:
        try:
            post = frontmatter.load(path)
            self._skill_md[name] = dict(post.metadata)
            self._skill_md_content[name] = post.content
        except Exception:
            logger.exception("Failed to load SKILL.md for %s", name)

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def get_skill_md(self, name: str) -> Optional[str]:
        return self._skill_md_content.get(name)

    def get_skill_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        return self._skill_md.get(name)

    def all_skills(self) -> List[Skill]:
        return list(self._skills.values())

    def match_event(self, event: DataEvent) -> List[Skill]:
        matched: List[Skill] = []
        for name, skill in self._skills.items():
            trigger = skill.trigger()
            if trigger not in (SkillTrigger.EVENT, SkillTrigger.BOTH):
                continue

            event_filter = skill.event_filter()
            if event_filter is None:
                # Match by required_data resource types
                required = skill.required_data()
                resource_types = {r.resource_type for r in required.values()}
                if event.resource_type in resource_types:
                    matched.append(skill)
                continue

            # Match by event_filter
            resource_match = event_filter.get("resource_type")
            code_prefix = event_filter.get("code_prefix")

            if resource_match and event.resource_type != resource_match:
                continue

            if code_prefix and event.resource_data:
                codes = event.resource_data.get("code", {}).get("coding", [])
                code_values = [c.get("code", "") for c in codes]
                if not any(c.startswith(code_prefix) for c in code_values):
                    continue

            matched.append(skill)

        return matched

    def all_event_types(self) -> List[str]:
        types: Set[str] = set()
        for skill in self._skills.values():
            for req in skill.required_data().values():
                types.add(req.resource_type)
        return sorted(types)

    def check_gating(
        self,
        skill: Skill,
        resource_manager: ResourceManager,
        adapter: Optional[DataAdapter] = None,
    ) -> tuple[bool, str]:
        """Check if a skill can run. Returns (can_run, reason)."""
        name = skill.name()
        md = self._skill_md.get(name, {})
        requires = md.get("requires", {})

        # Check adapter features
        if adapter and requires.get("adapter_features"):
            for feature in requires["adapter_features"]:
                if not adapter.supports(feature):
                    return False, f"adapter missing feature: {feature}"

        # Check resource types
        if adapter and requires.get("resources"):
            for rt in requires["resources"]:
                if not adapter.has_resource_type(rt):
                    return False, f"adapter missing resource type: {rt}"

        return True, ""


def load_skill_directory(path: str) -> List[Skill]:
    """Stub for Phase 1. Full implementation in Phase 2."""
    logger.info("load_skill_directory is a Phase 1 stub, returning empty list")
    return []
