"""Tests for all 5 IDSR skills: cholera, measles, meningitis, yellow fever, ebola.

Three patterns per skill:
1. LLM path with reflection validation
2. Hallucination detection (LLM fabricates data, reflection catches it)
3. Degraded mode (rules-only fallback)
"""

import importlib.util
import sys
from pathlib import Path

from open_sentinel.llm.mock import MockLLMEngine
from open_sentinel.testing.harness import SkillTestHarness
from open_sentinel.types import AgentConfig

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _import_skill(folder: str, module_name: str):
    """Import a skill module from a hyphenated skill directory."""
    spec = importlib.util.spec_from_file_location(
        module_name, _SKILLS_DIR / folder / "skill.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_cholera_mod = _import_skill("idsr-cholera", "idsr_cholera_skill")
_measles_mod = _import_skill("idsr-measles", "idsr_measles_skill")
_meningitis_mod = _import_skill("idsr-meningitis", "idsr_meningitis_skill")
_yf_mod = _import_skill("idsr-yellow-fever", "idsr_yellow_fever_skill")
_ebola_mod = _import_skill("idsr-ebola", "idsr_ebola_skill")

IdsrCholeraSkill = _cholera_mod.IdsrCholeraSkill
IdsrMeaslesSkill = _measles_mod.IdsrMeaslesSkill
IdsrMeningitisSkill = _meningitis_mod.IdsrMeningitisSkill
IdsrYellowFeverSkill = _yf_mod.IdsrYellowFeverSkill
IdsrEbolaSkill = _ebola_mod.IdsrEbolaSkill


_CONFIG = AgentConfig(state_db_path=":memory:", hardware="hub_16gb")


# ============================================================
# Cholera Tests
# ============================================================


class TestIdsrCholeraLLM:
    async def test_llm_path_with_reflection(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "Cholera outbreak at clinic-01",
                "description": "New cholera cases detected",
                "site_id": "clinic-01",
                "measured_value": 3,
                "confidence": 0.9,
                "evidence": {"site_id": "clinic-01", "value": 3},
                "dedup_key": "idsr-cholera-clinic-01-2026-W09",
            }]}
        ])
        harness = SkillTestHarness(skill=IdsrCholeraSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "cholera_this_week": [{"site_id": "clinic-01", "value": 3}],
            "cholera_12w": [],
            "diarrhoeal_4w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert not result.degraded
        assert len(result.alerts) >= 1
        assert result.alerts[0].ai_generated is True
        assert result.alerts[0].requires_review is True
        assert result.alerts[0].severity == "critical"


class TestIdsrCholeraHallucination:
    async def test_hallucination_detected(self):
        llm = MockLLMEngine(responses=[
            # First: LLM hallucinates 20 cases
            {"findings": [{
                "severity": "critical",
                "title": "Cholera at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 20,
                "confidence": 0.9,
                "evidence": {"site_id": "clinic-01", "value": 20},
                "dedup_key": "idsr-cholera-clinic-01-2026-W09",
            }]},
            # Second: corrected after reflection
            {"findings": [{
                "severity": "critical",
                "title": "Cholera at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 2,
                "confidence": 0.85,
                "evidence": {"site_id": "clinic-01", "value": 2},
                "dedup_key": "idsr-cholera-clinic-01-2026-W09",
            }]},
        ])
        harness = SkillTestHarness(skill=IdsrCholeraSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "cholera_this_week": [{"site_id": "clinic-01", "value": 2}],
            "cholera_12w": [],
            "diarrhoeal_4w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.reflection_count >= 1
        assert any(c["method"] == "reflect" for c in llm.call_history)


class TestIdsrCholeraDegraded:
    async def test_rules_only_zero_baseline(self):
        llm = MockLLMEngine(is_available=False)
        harness = SkillTestHarness(skill=IdsrCholeraSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "cholera_this_week": [{"site_id": "clinic-01", "value": 3}],
            "cholera_12w": [],
            "diarrhoeal_4w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.degraded is True
        assert result.reflection_count == 0
        assert len(result.alerts) == 1
        alert = result.alerts[0]
        assert alert.ai_generated is False
        assert alert.rule_validated is True
        assert alert.requires_review is True
        assert alert.severity == "critical"
        assert "clinic-01" in alert.title


# ============================================================
# Measles Tests
# ============================================================


class TestIdsrMeaslesLLM:
    async def test_llm_path(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "Measles cluster at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 5,
                "confidence": 0.88,
                "evidence": {"site_id": "clinic-01", "value": 5},
                "dedup_key": "idsr-measles-clinic-01-2026-W09",
            }]}
        ])
        harness = SkillTestHarness(skill=IdsrMeaslesSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "measles_4w": [{"site_id": "clinic-01", "value": 5}],
            "measles_12w": [],
            "immunization_coverage": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert not result.degraded
        assert len(result.alerts) >= 1
        assert result.alerts[0].ai_generated is True


class TestIdsrMeaslesHallucination:
    async def test_hallucination_detected(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "Measles at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 50,
                "confidence": 0.9,
                "evidence": {"site_id": "clinic-01", "value": 50},
                "dedup_key": "idsr-measles-clinic-01-2026-W09",
            }]},
            {"findings": [{
                "severity": "critical",
                "title": "Measles at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 3,
                "confidence": 0.85,
                "evidence": {"site_id": "clinic-01", "value": 3},
                "dedup_key": "idsr-measles-clinic-01-2026-W09",
            }]},
        ])
        harness = SkillTestHarness(skill=IdsrMeaslesSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "measles_4w": [{"site_id": "clinic-01", "value": 3}],
            "measles_12w": [],
            "immunization_coverage": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.reflection_count >= 1


class TestIdsrMeaslesDegraded:
    async def test_rules_cluster_threshold(self):
        llm = MockLLMEngine(is_available=False)
        harness = SkillTestHarness(skill=IdsrMeaslesSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "measles_4w": [{"site_id": "clinic-01", "value": 4}],
            "measles_12w": [],
            "immunization_coverage": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.degraded is True
        assert len(result.alerts) >= 1
        alert = result.alerts[0]
        assert alert.ai_generated is False
        assert alert.rule_validated is True
        assert alert.severity == "critical"


# ============================================================
# Meningitis Tests
# ============================================================


class TestIdsrMeningitisLLM:
    async def test_llm_path(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "Meningitis at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 2,
                "confidence": 0.87,
                "evidence": {"site_id": "clinic-01", "value": 2},
                "dedup_key": "idsr-meningitis-clinic-01-2026-W09",
            }]}
        ])
        harness = SkillTestHarness(skill=IdsrMeningitisSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "meningitis_4w": [{"site_id": "clinic-01", "value": 2}],
            "meningitis_12w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert not result.degraded
        assert len(result.alerts) >= 1
        assert result.alerts[0].ai_generated is True


class TestIdsrMeningitisHallucination:
    async def test_hallucination_detected(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "Meningitis at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 30,
                "confidence": 0.9,
                "evidence": {"site_id": "clinic-01", "value": 30},
                "dedup_key": "idsr-meningitis-clinic-01-2026-W09",
            }]},
            {"findings": [{
                "severity": "critical",
                "title": "Meningitis at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 2,
                "confidence": 0.85,
                "evidence": {"site_id": "clinic-01", "value": 2},
                "dedup_key": "idsr-meningitis-clinic-01-2026-W09",
            }]},
        ])
        harness = SkillTestHarness(skill=IdsrMeningitisSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "meningitis_4w": [{"site_id": "clinic-01", "value": 2}],
            "meningitis_12w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.reflection_count >= 1


class TestIdsrMeningitisDegraded:
    async def test_rules_zero_baseline(self):
        llm = MockLLMEngine(is_available=False)
        harness = SkillTestHarness(skill=IdsrMeningitisSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "meningitis_4w": [{"site_id": "clinic-01", "value": 1}],
            "meningitis_12w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.degraded is True
        assert len(result.alerts) >= 1
        alert = result.alerts[0]
        assert alert.ai_generated is False
        assert alert.rule_validated is True
        assert alert.severity == "critical"


# ============================================================
# Yellow Fever Tests
# ============================================================


class TestIdsrYellowFeverLLM:
    async def test_llm_path(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "Yellow fever at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 1,
                "confidence": 0.92,
                "evidence": {"site_id": "clinic-01", "value": 1},
                "dedup_key": "idsr-yellow-fever-clinic-01-2026-W09",
            }]}
        ])
        harness = SkillTestHarness(skill=IdsrYellowFeverSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "yf_cases_4w": [{"site_id": "clinic-01", "value": 1}],
            "yf_cases_12w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert not result.degraded
        assert len(result.alerts) >= 1
        assert result.alerts[0].ai_generated is True


class TestIdsrYellowFeverHallucination:
    async def test_hallucination_detected(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "Yellow fever at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 15,
                "confidence": 0.9,
                "evidence": {"site_id": "clinic-01", "value": 15},
                "dedup_key": "idsr-yellow-fever-clinic-01-2026-W09",
            }]},
            {"findings": [{
                "severity": "critical",
                "title": "Yellow fever at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 1,
                "confidence": 0.88,
                "evidence": {"site_id": "clinic-01", "value": 1},
                "dedup_key": "idsr-yellow-fever-clinic-01-2026-W09",
            }]},
        ])
        harness = SkillTestHarness(skill=IdsrYellowFeverSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "yf_cases_4w": [{"site_id": "clinic-01", "value": 1}],
            "yf_cases_12w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.reflection_count >= 1


class TestIdsrYellowFeverDegraded:
    async def test_rules_zero_tolerance(self):
        llm = MockLLMEngine(is_available=False)
        harness = SkillTestHarness(skill=IdsrYellowFeverSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "yf_cases_4w": [{"site_id": "clinic-01", "value": 1}],
            "yf_cases_12w": [],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.degraded is True
        assert len(result.alerts) == 1
        alert = result.alerts[0]
        assert alert.ai_generated is False
        assert alert.rule_validated is True
        assert alert.severity == "critical"
        assert "yellow fever" in alert.title.lower()


# ============================================================
# Ebola Tests
# ============================================================


class TestIdsrEbolaLLM:
    async def test_llm_path(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "EVD detected at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 1,
                "confidence": 0.95,
                "evidence": {"site_id": "clinic-01", "value": 1},
                "dedup_key": "idsr-ebola-clinic-01-2026-W09",
            }]}
        ])
        harness = SkillTestHarness(skill=IdsrEbolaSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "evd_cases": [{"site_id": "clinic-01", "value": 1}],
            "hemorrhagic_fever_4w": [{"site_id": "clinic-01", "value": 1}],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert not result.degraded
        assert len(result.alerts) >= 1
        assert result.alerts[0].ai_generated is True


class TestIdsrEbolaHallucination:
    async def test_hallucination_detected(self):
        llm = MockLLMEngine(responses=[
            {"findings": [{
                "severity": "critical",
                "title": "EVD at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 10,
                "confidence": 0.9,
                "evidence": {"site_id": "clinic-01", "value": 10},
                "dedup_key": "idsr-ebola-clinic-01-2026-W09",
            }]},
            {"findings": [{
                "severity": "critical",
                "title": "EVD at clinic-01",
                "site_id": "clinic-01",
                "measured_value": 1,
                "confidence": 0.9,
                "evidence": {"site_id": "clinic-01", "value": 1},
                "dedup_key": "idsr-ebola-clinic-01-2026-W09",
            }]},
        ])
        harness = SkillTestHarness(skill=IdsrEbolaSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "evd_cases": [{"site_id": "clinic-01", "value": 1}],
            "hemorrhagic_fever_4w": [{"site_id": "clinic-01", "value": 1}],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.reflection_count >= 1


class TestIdsrEbolaDegraded:
    async def test_rules_zero_tolerance_evd(self):
        llm = MockLLMEngine(is_available=False)
        harness = SkillTestHarness(skill=IdsrEbolaSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "evd_cases": [{"site_id": "clinic-01", "value": 1}],
            "hemorrhagic_fever_4w": [{"site_id": "clinic-01", "value": 1}],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.degraded is True
        assert len(result.alerts) >= 1
        evd_alert = [
            a for a in result.alerts
            if "ebola" in a.title.lower() or "evd" in a.title.lower()
        ]
        assert len(evd_alert) >= 1
        assert evd_alert[0].ai_generated is False
        assert evd_alert[0].rule_validated is True
        assert evd_alert[0].severity == "critical"

    async def test_rules_hemorrhagic_sentinel(self):
        llm = MockLLMEngine(is_available=False)
        harness = SkillTestHarness(skill=IdsrEbolaSkill(), llm=llm, config=_CONFIG)
        harness.set_data({
            "evd_cases": [],
            "hemorrhagic_fever_4w": [{"site_id": "clinic-01", "value": 3}],
        }).set_site_id("clinic-01")

        result = await harness.run_async()
        assert result.degraded is True
        assert len(result.alerts) >= 1
        alert = result.alerts[0]
        assert alert.severity == "high"
        assert alert.rule_validated is True
