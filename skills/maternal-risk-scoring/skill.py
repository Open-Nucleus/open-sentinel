"""Maternal risk scoring skill."""

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

# LOINC codes for maternal vitals
_BP_SYSTOLIC_LOINC = "8480-6"
_BP_DIASTOLIC_LOINC = "8462-4"
_PLATELET_LOINC = "777-3"


class MaternalRiskScoringSkill(Skill):
    def name(self) -> str:
        return "maternal-risk-scoring"

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.EVENT

    def priority(self) -> Priority:
        return Priority.HIGH

    def event_filter(self) -> Optional[Dict[str, Any]]:
        return {"resource_type": "Observation"}

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "ob_conditions": DataRequirement(
                resource_type="Condition",
                filters={"code_prefix": "O"},
                name="ob_conditions",
            ),
            "vitals": DataRequirement(
                resource_type="Observation",
                filters={"code": f"{_BP_SYSTOLIC_LOINC},{_BP_DIASTOLIC_LOINC},{_PLATELET_LOINC}"},
                time_window="4w",
                name="vitals",
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
        return "Identify high-risk maternal patients requiring urgent intervention"

    def build_prompt(self, ctx: AnalysisContext) -> str:
        conditions = extract_records(ctx, "ob_conditions")
        vitals = extract_records(ctx, "vitals")
        patients = extract_records(ctx, "patients")

        lines = ["## Maternal Health Data\n"]
        lines.append(f"### Obstetric Conditions (O-codes): {len(conditions)}")
        for c in conditions[:20]:
            pid = c.get("patient_id", c.get("subject", {}).get("reference", "unknown"))
            code = c.get("code", "O")
            lines.append(f"- Patient {pid}: {code}")

        lines.append(f"\n### Vital Signs (4w): {len(vitals)}")
        for v in vitals[:30]:
            pid = v.get("patient_id", v.get("subject", {}).get("reference", "unknown"))
            code = v.get("code", v.get("loinc", ""))
            value = v.get("value", "")
            lines.append(f"- Patient {pid}: {code} = {value}")

        lines.append(f"\n### Patients: {len(patients)}")

        lines.append("\n### Analysis Required")
        lines.append("1. Check BP trajectories per patient (systolic >160, diastolic >110)")
        lines.append("2. Check platelet counts (<100k)")
        lines.append("3. Identify 2+ concurrent abnormals (pre-eclampsia/HELLP signal)")
        lines.append("4. Synthesise multi-factor risk score")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        vitals = extract_records(ctx, "vitals")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        # Group vitals by patient
        by_patient: Dict[str, Dict[str, float]] = {}
        for v in vitals:
            pid = v.get("patient_id", v.get("subject", {}).get("reference", ""))
            if not pid:
                continue
            code = str(v.get("code", v.get("loinc", "")))
            value = v.get("value")
            if value is None:
                continue
            try:
                value = float(value)
            except (ValueError, TypeError):
                continue

            by_patient.setdefault(pid, {})
            # Keep the most extreme value per code
            if code in by_patient[pid]:
                if code == _PLATELET_LOINC:
                    by_patient[pid][code] = min(by_patient[pid][code], value)
                else:
                    by_patient[pid][code] = max(by_patient[pid][code], value)
            else:
                by_patient[pid][code] = value

        for pid, patient_vitals in by_patient.items():
            abnormals = []

            systolic = patient_vitals.get(_BP_SYSTOLIC_LOINC)
            diastolic = patient_vitals.get(_BP_DIASTOLIC_LOINC)
            platelets = patient_vitals.get(_PLATELET_LOINC)

            if systolic is not None and systolic > 160:
                abnormals.append(f"systolic BP {systolic}")
            if diastolic is not None and diastolic > 110:
                abnormals.append(f"diastolic BP {diastolic}")
            if platelets is not None and platelets < 100000:
                abnormals.append(f"platelets {platelets}")

            if len(abnormals) >= 2:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="critical",
                    category="maternal-health",
                    title=f"Pre-eclampsia/HELLP risk for patient {pid}",
                    description=(
                        f"Patient {pid} has {len(abnormals)} concurrent abnormals: "
                        f"{', '.join(abnormals)}. Urgent evaluation for pre-eclampsia/HELLP."
                    ),
                    patient_id=pid,
                    site_id=ctx.site_id,
                    evidence={
                        "patient_id": pid,
                        "abnormals": abnormals,
                        "systolic": systolic,
                        "diastolic": diastolic,
                        "platelets": platelets,
                    },
                    measured_value=float(len(abnormals)),
                    threshold_value=2.0,
                    dedup_key=patient_dedup_key(self.name(), pid, now),
                    rule_validated=True,
                ))
            elif len(abnormals) == 1:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="maternal-health",
                    title=f"Maternal risk for patient {pid}: {abnormals[0]}",
                    description=(
                        f"Patient {pid} has abnormal: {abnormals[0]}. "
                        f"Monitor closely for progression."
                    ),
                    patient_id=pid,
                    site_id=ctx.site_id,
                    evidence={
                        "patient_id": pid,
                        "abnormals": abnormals,
                        "systolic": systolic,
                        "diastolic": diastolic,
                        "platelets": platelets,
                    },
                    dedup_key=patient_dedup_key(self.name(), pid, now),
                    rule_validated=True,
                ))

        return alerts

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        return critique_patient_findings(findings, ctx, "vitals")
