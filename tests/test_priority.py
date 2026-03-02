"""Tests for PriorityQueue."""

from open_sentinel.priority import PriorityQueue
from open_sentinel.types import Alert, Priority


class _MockSkill:
    def __init__(self, skill_name: str, skill_priority: Priority):
        self._name = skill_name
        self._priority = skill_priority

    def name(self) -> str:
        return self._name

    def priority(self) -> Priority:
        return self._priority


class TestPriorityQueue:
    def test_rank_skills_by_priority(self):
        pq = PriorityQueue()
        skills = [
            _MockSkill("low-skill", Priority.LOW),
            _MockSkill("critical-skill", Priority.CRITICAL),
            _MockSkill("medium-skill", Priority.MEDIUM),
        ]
        ranked = pq.rank_skills(skills)
        assert ranked[0].name() == "critical-skill"
        assert ranked[1].name() == "medium-skill"
        assert ranked[2].name() == "low-skill"

    def test_rank_skills_tiebreak_by_name(self):
        pq = PriorityQueue()
        skills = [
            _MockSkill("zebra", Priority.HIGH),
            _MockSkill("alpha", Priority.HIGH),
        ]
        ranked = pq.rank_skills(skills)
        assert ranked[0].name() == "alpha"
        assert ranked[1].name() == "zebra"

    def test_rank_alerts(self):
        pq = PriorityQueue()
        alerts = [
            Alert(severity="low", title="Low"),
            Alert(severity="critical", title="Crit"),
            Alert(severity="moderate", title="Med"),
            Alert(severity="high", title="High"),
        ]
        ranked = pq.rank_alerts(alerts)
        assert ranked[0].severity == "critical"
        assert ranked[1].severity == "high"
        assert ranked[2].severity == "moderate"
        assert ranked[3].severity == "low"

    def test_empty_lists(self):
        pq = PriorityQueue()
        assert pq.rank_skills([]) == []
        assert pq.rank_alerts([]) == []
