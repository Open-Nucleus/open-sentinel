"""Tests for load_skill_directory()."""

import textwrap
from pathlib import Path

from open_sentinel.registry import load_skill_directory


class TestLoadSkillDirectory:
    def test_loads_valid_skill(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.py").write_text(textwrap.dedent("""\
            from open_sentinel.interfaces import Skill
            from open_sentinel.types import Alert, AnalysisContext, DataRequirement

            class TestSkill(Skill):
                def name(self): return "test-skill"
                def required_data(self): return {"data": DataRequirement(resource_type="Condition")}
                def build_prompt(self, ctx): return "Test"
                def rule_fallback(self, ctx): return []
        """))
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\n---\n# Test")

        skills = load_skill_directory(str(tmp_path))
        assert len(skills) == 1
        assert skills[0].name() == "test-skill"

    def test_attaches_skill_md_path(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.py").write_text(textwrap.dedent("""\
            from open_sentinel.interfaces import Skill
            from open_sentinel.types import Alert, AnalysisContext, DataRequirement

            class TestSkill(Skill):
                def name(self): return "test-skill"
                def required_data(self): return {"data": DataRequirement(resource_type="Condition")}
                def build_prompt(self, ctx): return "Test"
                def rule_fallback(self, ctx): return []
        """))
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\nname: test-skill\n---\n# Test")

        skills = load_skill_directory(str(tmp_path))
        assert hasattr(skills[0].__class__, "__skill_md_path__")
        assert skills[0].__class__.__skill_md_path__ == str(skill_md)

    def test_empty_directory_returns_empty(self, tmp_path):
        skills = load_skill_directory(str(tmp_path))
        assert skills == []

    def test_nonexistent_directory_returns_empty(self, tmp_path):
        skills = load_skill_directory(str(tmp_path / "nonexistent"))
        assert skills == []

    def test_invalid_skill_skipped(self, tmp_path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.py").write_text("raise ImportError('broken')")

        skills = load_skill_directory(str(tmp_path))
        assert skills == []

    def test_directory_without_skill_py_skipped(self, tmp_path):
        (tmp_path / "no-code").mkdir()
        (tmp_path / "no-code" / "SKILL.md").write_text("# No skill.py")

        skills = load_skill_directory(str(tmp_path))
        assert skills == []

    def test_loads_multiple_skills(self, tmp_path):
        for name in ["skill-a", "skill-b"]:
            skill_dir = tmp_path / name
            skill_dir.mkdir()
            class_name = name.replace("-", "_").title().replace("_", "")
            (skill_dir / "skill.py").write_text(textwrap.dedent(f"""\
                from open_sentinel.interfaces import Skill
                from open_sentinel.types import Alert, AnalysisContext, DataRequirement

                class {class_name}Skill(Skill):
                    def name(self): return "{name}"
                    def required_data(self):
                        return {{"data": DataRequirement(resource_type="Condition")}}
                    def build_prompt(self, ctx): return "Test"
                    def rule_fallback(self, ctx): return []
            """))

        skills = load_skill_directory(str(tmp_path))
        assert len(skills) == 2
        names = {s.name() for s in skills}
        assert names == {"skill-a", "skill-b"}

    def test_loads_real_skills_directory(self):
        """Verify load_skill_directory loads the actual project skills."""
        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        if skills_dir.exists():
            skills = load_skill_directory(str(skills_dir))
            # Should load all 13 skills (5 IDSR + 8 clinical/supply)
            assert len(skills) >= 13
            names = {s.name() for s in skills}
            assert "idsr-cholera" in names
            assert "medication-missed-dose" in names
            assert "vital-sign-trend" in names
