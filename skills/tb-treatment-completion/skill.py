"""TB treatment completion monitoring skill."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from open_sentinel.interfaces import Skill
from open_sentinel.skills.clinical_base import (
    CLINICAL_RESPONSE_SCHEMA,
    critique_patient_findings,
    extract_records,
    patient_dedup_key,
)
from open_sentinel.types import Alert, AnalysisContext, DataRequirement, Priority, SkillTrigger

_TB_MEDICATIONS = {"rifampicin", "isoniazid", "pyrazinamide", "ethambutol"}


class TbTreatmentCompletionSkill(Skill):
    def name(self) -> str:
        return "tb-treatment-completion"

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.SCHEDULE

    def schedule(self) -> Optional[str]:
        return "0 6 * * 1"

    def priority(self) -> Priority:
        return Priority.MEDIUM

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "tb_conditions": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "A15"},
                name="tb_conditions",
            ),
            "tb_medications": DataRequirement(
                resource_type="MedicationRequest",
                filters={"medication_contains": "rifampicin,isoniazid,pyrazinamide,ethambutol"},
                time_window="24w",
                name="tb_medications",
            ),
            "care_plans": DataRequirement(
                resource_type="CarePlan",
                filters={"category": "TB"},
                name="care_plans",
            ),
        }

    def response_schema(self) -> Optional[Dict[str, Any]]:
        return CLINICAL_RESPONSE_SCHEMA

    def max_reflections(self) -> int:
        return 2

    def goal(self) -> str:
        return "Monitor TB treatment completion and detect abandonment risk"

    def build_prompt(self, ctx: AnalysisContext) -> str:
        conditions = extract_records(ctx, "tb_conditions")
        medications = extract_records(ctx, "tb_medications")
        care_plans = extract_records(ctx, "care_plans")

        lines = ["## TB Treatment Data\n"]
        lines.append(f"### Active TB Conditions (A15): {len(conditions)}")
        for c in conditions[:20]:
            pid = c.get("patient_id", c.get("subject", {}).get("reference", "unknown"))
            lines.append(f"- Patient {pid}: {c.get('code', 'A15')}")

        lines.append(f"\n### TB Medications (24w): {len(medications)}")
        for m in medications[:20]:
            pid = m.get("patient_id", m.get("subject", {}).get("reference", "unknown"))
            med = m.get("medication", "unknown")
            date = m.get("authored_on", m.get("authoredOn", "unknown"))
            lines.append(f"- Patient {pid}: {med} dispensed {date}")

        lines.append(f"\n### Care Plans: {len(care_plans)}")
        for cp in care_plans[:20]:
            pid = cp.get("patient_id", cp.get("subject", {}).get("reference", "unknown"))
            status = cp.get("status", "unknown")
            lines.append(f"- Patient {pid}: status={status}")

        lines.append("\n### Analysis Required")
        lines.append("1. Identify patients with active TB + active care plan but no recent meds")
        lines.append("2. Calculate days since last dispensing per patient")
        lines.append("3. Assess treatment phase and abandonment risk")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        medications = extract_records(ctx, "tb_medications")
        care_plans = extract_records(ctx, "care_plans")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        # Active TB care plan patients
        active_cp_patients = set()
        for cp in care_plans:
            if cp.get("status", "").lower() == "active":
                pid = cp.get("patient_id", cp.get("subject", {}).get("reference", ""))
                if pid:
                    active_cp_patients.add(pid)

        # Find last dispensed date per patient
        last_dispensed: Dict[str, datetime] = {}
        for m in medications:
            pid = m.get("patient_id", m.get("subject", {}).get("reference", ""))
            if not pid:
                continue
            date_str = m.get("authored_on", m.get("authoredOn", ""))
            if date_str:
                try:
                    if isinstance(date_str, str):
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                    elif isinstance(date_str, datetime):
                        dt = date_str
                    else:
                        continue
                    if pid not in last_dispensed or dt > last_dispensed[pid]:
                        last_dispensed[pid] = dt
                except (ValueError, TypeError):
                    continue

        for pid in active_cp_patients:
            last_date = last_dispensed.get(pid)
            if last_date is None:
                # Active care plan but no medication records at all
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="tb",
                    title=f"TB treatment gap for patient {pid} (no recent dispensing)",
                    description=(
                        f"Patient {pid} has active TB care plan but no medication "
                        f"dispensing records found. Treatment abandonment risk."
                    ),
                    patient_id=pid,
                    site_id=ctx.site_id,
                    evidence={"patient_id": pid, "last_dispensed": None},
                    dedup_key=patient_dedup_key(self.name(), pid, now),
                    rule_validated=True,
                ))
            elif (now - last_date) > timedelta(days=14):
                days_since = (now - last_date).days
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="tb",
                    title=f"TB treatment gap for patient {pid} ({days_since}d since last dose)",
                    description=(
                        f"Patient {pid} last dispensed TB medication {days_since} days ago "
                        f"but has active care plan. Treatment abandonment risk."
                    ),
                    patient_id=pid,
                    site_id=ctx.site_id,
                    evidence={
                        "patient_id": pid,
                        "days_since_last": days_since,
                        "last_dispensed": last_date.isoformat(),
                    },
                    measured_value=float(days_since),
                    threshold_value=14.0,
                    dedup_key=patient_dedup_key(self.name(), pid, now),
                    rule_validated=True,
                ))

        return alerts

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        return critique_patient_findings(findings, ctx, "tb_conditions")
