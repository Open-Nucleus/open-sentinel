"""Immunisation gap detection skill."""

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

# (vaccine_name, due_days_after_birth)
_EPI_SCHEDULE = [
    ("BCG", 0),
    ("OPV0", 0),
    ("Penta1", 42),
    ("OPV1", 42),
    ("Penta2", 70),
    ("OPV2", 70),
    ("Penta3", 98),
    ("OPV3", 98),
    ("Measles1", 270),
    ("Measles2", 450),
]

_OVERDUE_THRESHOLD_DAYS = 28  # 4 weeks


class ImmunisationGapSkill(Skill):
    def name(self) -> str:
        return "immunisation-gap"

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.SCHEDULE

    def schedule(self) -> Optional[str]:
        return "0 6 * * 1"

    def priority(self) -> Priority:
        return Priority.MEDIUM

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "immunizations": DataRequirement(
                resource_type="Immunization",
                filters={"status": "completed"},
                time_window="104w",
                name="immunizations",
            ),
            "patients": DataRequirement(
                resource_type="Patient",
                filters={"active": True},
                name="patients",
            ),
        }

    def response_schema(self) -> Optional[Dict[str, Any]]:
        return CLINICAL_RESPONSE_SCHEMA

    def max_reflections(self) -> int:
        return 2

    def goal(self) -> str:
        return "Identify children with overdue immunisations per EPI schedule"

    def build_prompt(self, ctx: AnalysisContext) -> str:
        patients = extract_records(ctx, "patients")
        immunizations = extract_records(ctx, "immunizations")

        lines = ["## Immunisation Data\n"]
        lines.append(f"### Patients: {len(patients)}")
        for p in patients[:20]:
            pid = p.get("id", p.get("patient_id", "unknown"))
            dob = p.get("birthDate", p.get("birth_date", "unknown"))
            lines.append(f"- Patient {pid}: DOB {dob}")

        lines.append(f"\n### Completed Immunisations: {len(immunizations)}")
        for i in immunizations[:30]:
            pid = i.get("patient_id", i.get("patient", {}).get("reference", "unknown"))
            vaccine = i.get("vaccine_code", i.get("vaccineCode", "unknown"))
            date = i.get("occurrence", i.get("occurrenceDateTime", "unknown"))
            lines.append(f"- Patient {pid}: {vaccine} on {date}")

        lines.append("\n### Analysis Required")
        lines.append("1. Compare each child's received immunisations against EPI schedule")
        lines.append("2. Identify overdue doses (>4 weeks past due date)")
        lines.append("3. Generate catch-up recommendations")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        patients = extract_records(ctx, "patients")
        immunizations = extract_records(ctx, "immunizations")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        # Group immunizations by patient
        imm_by_patient: Dict[str, set] = {}
        for i in immunizations:
            pid = i.get("patient_id", i.get("patient", {}).get("reference", ""))
            vaccine = str(i.get("vaccine_code", i.get("vaccineCode", ""))).lower()
            if pid:
                imm_by_patient.setdefault(pid, set()).add(vaccine)

        for patient in patients:
            pid = patient.get("id", patient.get("patient_id", ""))
            dob_str = patient.get("birthDate", patient.get("birth_date"))
            if not pid or not dob_str:
                continue

            try:
                if isinstance(dob_str, str):
                    dob = datetime.fromisoformat(dob_str.replace("Z", "+00:00"))
                    if dob.tzinfo is None:
                        dob = dob.replace(tzinfo=timezone.utc)
                else:
                    continue
            except (ValueError, TypeError):
                continue

            received = imm_by_patient.get(pid, set())
            overdue: List[str] = []

            for vaccine_name, due_days in _EPI_SCHEDULE:
                due_date = dob + timedelta(days=due_days)
                threshold_date = due_date + timedelta(days=_OVERDUE_THRESHOLD_DAYS)

                if now > threshold_date and vaccine_name.lower() not in received:
                    overdue.append(vaccine_name)

            if overdue:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="moderate",
                    category="immunisation",
                    title=f"Overdue immunisations for patient {pid}",
                    description=(
                        f"Patient {pid} is overdue for: {', '.join(overdue)}. "
                        f"Catch-up vaccination recommended."
                    ),
                    patient_id=pid,
                    site_id=ctx.site_id,
                    evidence={
                        "patient_id": pid,
                        "overdue_vaccines": overdue,
                        "received_count": len(received),
                    },
                    measured_value=float(len(overdue)),
                    dedup_key=patient_dedup_key(self.name(), pid, now),
                    rule_validated=True,
                ))

        return alerts

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        return critique_patient_findings(findings, ctx, "patients")
