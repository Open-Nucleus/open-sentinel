"""IDSR Ebola virus disease detection skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from open_sentinel.skills.idsr_base import IdsrBaseSkill
from open_sentinel.types import Alert, AnalysisContext, DataRequirement


class IdsrEbolaSkill(IdsrBaseSkill):
    def name(self) -> str:
        return "idsr-ebola"

    def goal(self) -> str:
        return "Detect Ebola virus disease and hemorrhagic fever signals"

    def event_filter(self) -> dict | None:
        return {"resource_type": "Condition", "code_prefix": "A98"}

    def schedule(self) -> str | None:
        return "0 6 * * 1"

    def max_reflections(self) -> int:
        return 3

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "evd_cases": DataRequirement(
                resource_type="Condition",
                filters={"code": ["A98.3", "A98.4"]},
                time_window="12w",
                group_by=["site_id"],
                metric="count",
                name="evd_cases",
            ),
            "hemorrhagic_fever_4w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A98"},
                time_window="4w",
                group_by=["site_id"],
                metric="count",
                name="hemorrhagic_fever_4w",
            ),
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        evd = self._site_counts(ctx, "evd_cases")
        hemorrhagic = self._site_counts(ctx, "hemorrhagic_fever_4w")

        lines = ["## Ebola / Hemorrhagic Fever Surveillance Data\n"]
        lines.append("### Confirmed EVD Cases (A98.3, A98.4) by Site (12 weeks)")
        if evd:
            for site, count in sorted(evd.items()):
                lines.append(f"- {site}: {count} confirmed EVD cases")
        else:
            lines.append("- No confirmed EVD cases")

        lines.append("\n### Hemorrhagic Fever Cases (A98*) by Site (4 weeks)")
        if hemorrhagic:
            for site, count in sorted(hemorrhagic.items()):
                lines.append(f"- {site}: {count} hemorrhagic fever cases")
        else:
            lines.append("- No hemorrhagic fever cases reported")

        lines.append("\n### Analysis Required")
        lines.append("ZERO TOLERANCE for EVD: Any A98.3/A98.4 case → CRITICAL.")
        lines.append("1. Flag all EVD cases as CRITICAL immediately")
        lines.append(
            "2. Check for sentinel hemorrhagic fever signals"
            " (≥2 A98 with no confirmed EVD)"
        )
        lines.append("3. Consider contact tracing and geographic spread")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        evd = self._site_counts(ctx, "evd_cases")
        hemorrhagic = self._site_counts(ctx, "hemorrhagic_fever_4w")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        # Zero tolerance for confirmed EVD
        for site_id, count in evd.items():
            if count >= 1:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="epidemic",
                    title=f"Ebola virus disease detected at {site_id}",
                    description=(
                        f"{count} confirmed EVD case(s) at {site_id}. "
                        f"Zero tolerance per IDSR — immediate emergency response required."
                    ),
                    site_id=site_id,
                    evidence={"evd_count": count, "baseline": 0, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=1.0,
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))

        # Sentinel signal: hemorrhagic fever without confirmed EVD
        for site_id, count in hemorrhagic.items():
            evd_count = evd.get(site_id, 0)
            if count >= 2 and evd_count == 0:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="epidemic",
                    title=f"Hemorrhagic fever cluster at {site_id} (no confirmed EVD)",
                    description=(
                        f"{count} hemorrhagic fever cases at {site_id} with no confirmed EVD. "
                        f"Sentinel signal — EVD testing recommended."
                    ),
                    site_id=site_id,
                    evidence={"hemorrhagic_count": count, "evd_count": 0, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=2.0,
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))

        return alerts
