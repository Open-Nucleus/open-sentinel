"""IDSR Cholera outbreak detection skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from open_sentinel.skills.idsr_base import IdsrBaseSkill
from open_sentinel.types import Alert, AnalysisContext, DataRequirement


class IdsrCholeraSkill(IdsrBaseSkill):
    def name(self) -> str:
        return "idsr-cholera"

    def goal(self) -> str:
        return "Detect cholera outbreaks within 24 hours of first case"

    def event_filter(self) -> dict | None:
        return {"resource_type": "Condition", "code_prefix": "A00"}

    def schedule(self) -> str | None:
        return "0 6 * * 1"

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "cholera_12w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A00"},
                time_window="12w",
                group_by=["site_id", "week"],
                metric="count",
                name="cholera_12w",
            ),
            "cholera_this_week": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A00"},
                time_window="1w",
                group_by=["site_id"],
                metric="count",
                name="cholera_this_week",
            ),
            "diarrhoeal_4w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A0"},
                time_window="4w",
                group_by=["site_id"],
                metric="count",
                name="diarrhoeal_4w",
            ),
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        this_week = self._site_counts(ctx, "cholera_this_week")
        baseline_data = ctx.data.get("cholera_12w", [])
        diarrhoeal = self._site_counts(ctx, "diarrhoeal_4w")

        lines = ["## Cholera Surveillance Data\n"]
        lines.append("### Current Week Cases (A00) by Site")
        if this_week:
            for site, count in sorted(this_week.items()):
                lines.append(f"- {site}: {count} cases")
        else:
            lines.append("- No cholera cases reported this week")

        lines.append("\n### 12-Week Baseline Data")
        if baseline_data:
            for row in baseline_data[:20]:
                if isinstance(row, dict):
                    lines.append(f"- {row}")
        else:
            lines.append("- No historical data available")

        lines.append("\n### Diarrhoeal Disease Trends (4 weeks)")
        if diarrhoeal:
            for site, count in sorted(diarrhoeal.items()):
                lines.append(f"- {site}: {count} diarrhoeal cases")
        else:
            lines.append("- No diarrhoeal data available")

        lines.append("\n### Analysis Required")
        lines.append("1. Identify sites with new cholera cases (zero-to-one transition)")
        lines.append("2. Compare case counts to 12-week baselines")
        lines.append("3. Note diarrhoeal disease co-occurrence patterns")
        lines.append("4. Assess outbreak risk and assign severity per IDSR thresholds")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        this_week = self._site_counts(ctx, "cholera_this_week")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        for site_id, count in this_week.items():
            baseline = ctx.baselines.get(f"cholera-{site_id}", 0)

            if baseline == 0 and count >= 1:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="epidemic",
                    title=f"Cholera case detected at {site_id} (zero baseline)",
                    description=(
                        f"{count} cholera case(s) detected at {site_id} where "
                        f"the 12-week baseline is 0. Immediate investigation required per IDSR."
                    ),
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=0.0,
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))
            elif baseline > 0 and count > baseline * 2:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="epidemic",
                    title=f"Cholera surge at {site_id} ({count} vs baseline {baseline})",
                    description=(
                        f"Cholera cases at {site_id} ({count}) exceed 2x the "
                        f"12-week baseline ({baseline}). Outbreak investigation recommended."
                    ),
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=float(baseline * 2),
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))

        return alerts

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        """Cross-reference claimed counts against cholera_this_week data."""
        this_week = self._site_counts(ctx, "cholera_this_week")
        issues = []

        for finding in findings:
            site_id = finding.get("site_id")
            claimed = finding.get("measured_value")
            if site_id is None or claimed is None:
                continue

            actual = this_week.get(site_id)
            if actual is not None:
                if float(claimed) > actual * 2:
                    issues.append(
                        f"Finding claims {claimed} cases for {site_id} but data shows {actual}"
                    )

        if issues:
            return "REVISE: " + "; ".join(issues)
        return "ACCEPT"
