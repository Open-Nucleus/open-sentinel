"""IDSR Yellow Fever detection skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from open_sentinel.skills.idsr_base import IdsrBaseSkill
from open_sentinel.types import Alert, AnalysisContext, DataRequirement


class IdsrYellowFeverSkill(IdsrBaseSkill):
    def name(self) -> str:
        return "idsr-yellow-fever"

    def goal(self) -> str:
        return "Detect any suspected yellow fever case for immediate investigation"

    def event_filter(self) -> dict | None:
        return {"resource_type": "Condition", "code_prefix": "A95"}

    def schedule(self) -> str | None:
        return "0 6 * * 1"

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "yf_cases_4w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A95"},
                time_window="4w",
                group_by=["site_id"],
                metric="count",
                name="yf_cases_4w",
            ),
            "yf_cases_12w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A95"},
                time_window="12w",
                group_by=["site_id", "week"],
                metric="count",
                name="yf_cases_12w",
            ),
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        cases_4w = self._site_counts(ctx, "yf_cases_4w")

        lines = ["## Yellow Fever Surveillance Data\n"]
        lines.append("### Cases in Past 4 Weeks (A95) by Site")
        if cases_4w:
            for site, count in sorted(cases_4w.items()):
                lines.append(f"- {site}: {count} suspected cases")
        else:
            lines.append("- No yellow fever cases reported")

        lines.append("\n### Analysis Required")
        lines.append("ZERO TOLERANCE: Any suspected yellow fever case requires CRITICAL alert.")
        lines.append("1. Flag all sites with any case as CRITICAL")
        lines.append("2. Note geographic clustering for vector control")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        cases_4w = self._site_counts(ctx, "yf_cases_4w")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        for site_id, count in cases_4w.items():
            if count >= 1:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="epidemic",
                    title=f"Yellow fever case detected at {site_id}",
                    description=(
                        f"{count} suspected yellow fever case(s) at {site_id}. "
                        f"Zero tolerance per IDSR — immediate investigation required."
                    ),
                    site_id=site_id,
                    evidence={"current": count, "baseline": 0, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=1.0,
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))

        return alerts
