"""IDSR Meningitis outbreak detection skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from open_sentinel.skills.idsr_base import IdsrBaseSkill
from open_sentinel.types import Alert, AnalysisContext, DataRequirement


def _is_meningitis_season(dt: datetime) -> bool:
    """Dec–Jun is meningitis season in the African meningitis belt."""
    return dt.month >= 12 or dt.month <= 6


class IdsrMeningitisSkill(IdsrBaseSkill):
    def name(self) -> str:
        return "idsr-meningitis"

    def goal(self) -> str:
        return "Detect meningitis outbreaks with seasonal and belt-aware thresholds"

    def event_filter(self) -> dict | None:
        return {"resource_type": "Condition", "code_prefix": "A39"}

    def schedule(self) -> str | None:
        return "0 6 * * 1"

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "meningitis_4w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A39"},
                time_window="4w",
                group_by=["site_id"],
                metric="count",
                name="meningitis_4w",
            ),
            "meningitis_12w": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A39"},
                time_window="12w",
                group_by=["site_id", "week"],
                metric="count",
                name="meningitis_12w",
            ),
        }

    def build_prompt(self, ctx: AnalysisContext) -> str:
        cases_4w = self._site_counts(ctx, "meningitis_4w")
        now = datetime.now(timezone.utc)
        in_season = _is_meningitis_season(now)

        lines = ["## Meningitis Surveillance Data\n"]
        season_str = (
            "IN meningitis season (Dec-Jun)" if in_season
            else "Outside meningitis season"
        )
        lines.append(f"### Season Status: {season_str}")
        lines.append("\n### Cases in Past 4 Weeks by Site")
        if cases_4w:
            for site, count in sorted(cases_4w.items()):
                lines.append(f"- {site}: {count} cases")
        else:
            lines.append("- No meningitis cases reported")

        lines.append("\n### Analysis Required")
        lines.append("1. Apply season-appropriate IDSR thresholds")
        lines.append("2. Identify zero-to-one transitions")
        lines.append("3. Check for off-season clusters (≥2 cases)")
        lines.append("4. Compare against 12-week baseline")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        cases_4w = self._site_counts(ctx, "meningitis_4w")
        now = datetime.now(timezone.utc)
        in_season = _is_meningitis_season(now)
        alerts: List[Alert] = []

        for site_id, count in cases_4w.items():
            baseline = ctx.baselines.get(f"meningitis-{site_id}", 0)

            if count >= 1 and baseline == 0:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="epidemic",
                    title=f"Meningitis case detected at {site_id} (zero baseline)",
                    description=(
                        f"{count} meningitis case(s) at {site_id} where baseline is 0. "
                        f"Immediate investigation required per IDSR."
                    ),
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=0.0,
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))
            elif not in_season and count >= 2:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="epidemic",
                    title=f"Off-season meningitis cluster at {site_id} ({count} cases)",
                    description=(
                        f"{count} meningitis cases at {site_id} outside meningitis season. "
                        f"Off-season cluster threshold (≥2) exceeded."
                    ),
                    site_id=site_id,
                    evidence={
                        "current": count, "baseline": baseline,
                        "in_season": in_season, "site_id": site_id,
                    },
                    measured_value=float(count),
                    threshold_value=2.0,
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))
            elif baseline > 0 and count > baseline * 2:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="epidemic",
                    title=f"Meningitis surge at {site_id} ({count} vs baseline {baseline})",
                    description=(
                        f"Meningitis cases at {site_id} ({count}) exceed 2x baseline ({baseline})."
                    ),
                    site_id=site_id,
                    evidence={"current": count, "baseline": baseline, "site_id": site_id},
                    measured_value=float(count),
                    threshold_value=float(baseline * 2),
                    dedup_key=self._dedup_key(site_id, now),
                    rule_validated=True,
                ))

        return alerts
