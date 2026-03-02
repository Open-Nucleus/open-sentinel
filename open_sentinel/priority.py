"""Priority queue for skill ranking and alert ranking."""

from __future__ import annotations

from typing import List

from open_sentinel.interfaces import Skill
from open_sentinel.types import Alert


class PriorityQueue:
    def rank_skills(self, skills: List[Skill]) -> List[Skill]:
        return sorted(skills, key=lambda s: (-s.priority(), s.name()))

    def rank_alerts(self, alerts: List[Alert]) -> List[Alert]:
        severity_order = {"critical": 4, "high": 3, "moderate": 2, "low": 1}
        return sorted(
            alerts,
            key=lambda a: -severity_order.get(a.severity, 0),
        )
