"""Skill registry: registration, SKILL.md parsing, event matching, gating."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from pathlib import Path
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
    """Walk a directory, import skill.py from each subdirectory, return Skill instances."""
    root = Path(path)
    if not root.is_dir():
        logger.warning("Skill directory does not exist: %s", path)
        return []

    skills: List[Skill] = []
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        skill_py = subdir / "skill.py"
        if not skill_py.exists():
            continue

        module_name = f"_sentinel_skill_{subdir.name.replace('-', '_')}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(skill_py))
            if spec is None or spec.loader is None:
                logger.warning("Cannot create module spec for %s", skill_py)
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)

            # Find Skill subclasses in the module
            skill_md_path = subdir / "SKILL.md"
            for _, cls in inspect.getmembers(mod, inspect.isclass):
                if issubclass(cls, Skill) and cls is not Skill and cls.__module__ == module_name:
                    if skill_md_path.exists():
                        cls.__skill_md_path__ = str(skill_md_path)
                    instance = cls()
                    skills.append(instance)
                    logger.info("Loaded skill %s from %s", instance.name(), subdir.name)
        except Exception:
            logger.exception("Failed to load skill from %s", subdir.name)

    return skills
