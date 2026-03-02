"""Medication missed dose detection skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from open_sentinel.interfaces import Skill
from open_sentinel.skills.clinical_base import (
    CLINICAL_RESPONSE_SCHEMA,
    critique_patient_findings,
    extract_records,
    patient_dedup_key,
)
from open_sentinel.types import Alert, AnalysisContext, DataRequirement, Priority, SkillTrigger

_HIGH_STAKES = {"art", "arv", "antiretroviral", "tb", "rifampicin", "isoniazid",
                "pyrazinamide", "ethambutol", "insulin", "antihypertensive",
                "amlodipine", "enalapril", "losartan", "metformin"}


class MedicationMissedDoseSkill(Skill):
    def name(self) -> str:
        return "medication-missed-dose"

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.EVENT

    def priority(self) -> Priority:
        return Priority.HIGH

    def event_filter(self) -> Optional[Dict[str, Any]]:
        return {"resource_type": "MedicationAdministration"}

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "med_requests": DataRequirement(
                resource_type="MedicationRequest",
                filters={"status": "active"},
                time_window="4w",
                name="med_requests",
            ),
            "med_administrations": DataRequirement(
                resource_type="MedicationAdministration",
                filters={"status": "completed"},
                time_window="4w",
                name="med_administrations",
            ),
        }

    def response_schema(self) -> Optional[Dict[str, Any]]:
        return CLINICAL_RESPONSE_SCHEMA

    def max_reflections(self) -> int:
        return 2

    def goal(self) -> str:
        return "Detect patients with dangerous medication adherence gaps"

    def build_prompt(self, ctx: AnalysisContext) -> str:
        requests = extract_records(ctx, "med_requests")
        admins = extract_records(ctx, "med_administrations")

        lines = ["## Medication Adherence Data\n"]
        lines.append(f"### Active Medication Requests: {len(requests)}")
        for r in requests[:20]:
            pid = r.get("patient_id", r.get("subject", {}).get("reference", "unknown"))
            med = r.get("medication", r.get("medication_code", "unknown"))
            freq = r.get("frequency", r.get("dosage_instruction", "unknown"))
            lines.append(f"- Patient {pid}: {med} (frequency: {freq})")

        lines.append(f"\n### Completed Administrations: {len(admins)}")
        for a in admins[:30]:
            pid = a.get("patient_id", a.get("subject", {}).get("reference", "unknown"))
            med = a.get("medication", a.get("medication_code", "unknown"))
            date = a.get("effective_date", a.get("effectiveDateTime", "unknown"))
            lines.append(f"- Patient {pid}: {med} on {date}")

        lines.append("\n### Analysis Required")
        lines.append("1. Compare expected doses vs actual administrations per patient")
        lines.append("2. Identify consecutive missed doses")
        lines.append("3. Flag high-stakes medications (ART, TB, insulin, antihypertensive)")
        lines.append("4. Assess 4-week adherence trajectory")

        return "\n".join(lines)

    def _is_high_stakes(self, medication: str) -> bool:
        med_lower = medication.lower()
        return any(hs in med_lower for hs in _HIGH_STAKES)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        requests = extract_records(ctx, "med_requests")
        admins = extract_records(ctx, "med_administrations")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        # Group administrations by patient
        admin_by_patient: Dict[str, int] = {}
        for a in admins:
            pid = a.get("patient_id", a.get("subject", {}).get("reference", ""))
            if pid:
                admin_by_patient[pid] = admin_by_patient.get(pid, 0) + 1

        for req in requests:
            pid = req.get("patient_id", req.get("subject", {}).get("reference", ""))
            if not pid:
                continue
            medication = req.get("medication", req.get("medication_code", ""))
            frequency = req.get("frequency", 1)
            if isinstance(frequency, str):
                try:
                    frequency = int(frequency)
                except ValueError:
                    frequency = 1

            expected_doses = frequency * 4  # 4 weeks
            actual_doses = admin_by_patient.get(pid, 0)
            consecutive_missed = max(0, expected_doses - actual_doses)

            high_stakes = self._is_high_stakes(str(medication))

            if (high_stakes and consecutive_missed >= 3) or consecutive_missed >= 5:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="medication-safety",
                    title=f"Missed doses for patient {pid} ({medication})",
                    description=(
                        f"Patient {pid} has {consecutive_missed} missed doses of "
                        f"{medication} over 4 weeks. "
                        f"{'High-stakes medication. ' if high_stakes else ''}"
                        f"Adherence intervention recommended."
                    ),
                    patient_id=pid,
                    site_id=ctx.site_id,
                    evidence={
                        "patient_id": pid,
                        "medication": str(medication),
                        "consecutive_missed": consecutive_missed,
                        "high_stakes": high_stakes,
                    },
                    measured_value=float(consecutive_missed),
                    threshold_value=3.0 if high_stakes else 5.0,
                    dedup_key=patient_dedup_key(self.name(), pid, now),
                    rule_validated=True,
                ))

        return alerts

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        return critique_patient_findings(findings, ctx, "med_requests")
