"""IDSR Measles outbreak detection skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from open_sentinel.skills.idsr_base import IdsrBaseSkill
from open_sentinel.types import Alert, AnalysisContext, DataRequirement


class IdsrMeaslesSkill(IdsrBaseSkill):
    def name(self) -> str:
        return "idsr-measles"

    def goal(self) -> str:
        return "Detect measles outbreaks and immunization coverage gaps"

    def event_filter(self) -> dict | None:
        return {"resource_type": "Condition", "code_prefix": "B05"}

    def schedule(self) -> str | None:
        return "0 6 * * 1"

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "measles_4w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "B05"},
                time_window="4w",
                group_by=["site_id"],
                metric="count",
                name="measles_4w",
            ),
            "measles_12w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "B05"},
                time_window="12w",
                group_by=["site_id", "week"],
                metric="count",
                name="measles_12w",
            ),
            "immunization_coverage": DataRequirement(
                resource_type="Immunization",
                filters={"code_prefix": "B05"},
                time_window="12w",
                group_by=["site_id"],
                metric="count",
                name="immunization_coverage",
            ),
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        cases_4w = self._site_counts(ctx, "measles_4w")
        immunization = self._site_counts(ctx, "immunization_coverage")

        lines = ["## Measles Surveillance Data\n"]
        lines.append("### Cases in Past 4 Weeks (B05) by Site")
        if cases_4w:
            for site, count in sorted(cases_4w.items()):
                lines.append(f"- {site}: {count} cases")
        else:
            lines.append("- No measles cases reported")

        lines.append("\n### Immunization Coverage by Site")
        if immunization:
            for site, count in sorted(immunization.items()):
                lines.append(f"- {site}: {count} immunizations recorded")
        else:
            lines.append("- No immunization data available")

        lines.append("\n### Analysis Required")
        lines.append("1. Identify zero-to-one case transitions")
        lines.append("2. Identify clusters (≥3 cases in 4 weeks)")
        lines.append("3. Cross-reference with immunization coverage gaps")
        lines.append("4. Assess outbreak risk per IDSR thresholds")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        cases_4w = self._site_counts(ctx, "measles_4w")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        for site_id, count in cases_4w.items():
            baseline = ctx.baselines.get(f"measles-{site_id}", 0)

            if count >= 1 and baseline == 0:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="epidemic",
                    title=f"Measles case detected at {site_id} (zero baseline)",
                    description=(
                        f"{count} measles case(s) at {site_id} where baseline is 0. "
                        f"Immediate investigation required per IDSR."
                    ),
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=0.0,
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))
            elif count >= 3:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="epidemic",
                    title=f"Measles cluster at {site_id} ({count} cases in 4 weeks)",
                    description=(
                        f"{count} measles cases at {site_id} within 4 weeks. "
                        f"Cluster threshold (≥3) exceeded. Outbreak investigation required."
                    ),
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=3.0,
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))
            elif baseline > 0 and count > baseline * 2:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="epidemic",
                    title=f"Measles surge at {site_id} ({count} vs baseline {baseline})",
                    description=(
                        f"Measles cases at {site_id} ({count}) exceed 2x baseline ({baseline})."
                    ),
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=float(baseline * 2),
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))

        return alerts
