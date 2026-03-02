"""Retrospective medication interaction detection skill."""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from open_sentinel.interfaces import Skill
from open_sentinel.skills.clinical_base import (
    CLINICAL_RESPONSE_SCHEMA,
    critique_patient_findings,
    extract_records,
    patient_dedup_key,
)
from open_sentinel.types import Alert, AnalysisContext, DataRequirement, Priority, SkillTrigger

_KNOWN_INTERACTIONS: Dict[FrozenSet[str], Tuple[str, str]] = {
    frozenset({"rifampicin", "efavirenz"}): (
        "high", "Rifampicin reduces efavirenz levels — ART efficacy compromised"
    ),
    frozenset({"rifampicin", "nevirapine"}): (
        "high", "Rifampicin reduces nevirapine levels — ART failure risk"
    ),
    frozenset({"metformin", "contrast"}): (
        "high", "Metformin with contrast agents — lactic acidosis risk"
    ),
    frozenset({"warfarin", "ibuprofen"}): (
        "high", "Warfarin + NSAID — increased bleeding risk"
    ),
    frozenset({"warfarin", "aspirin"}): (
        "moderate", "Warfarin + aspirin — bleeding risk, monitor INR"
    ),
    frozenset({"enalapril", "spironolactone"}): (
        "high", "ACE inhibitor + K-sparing diuretic — hyperkalemia risk"
    ),
    frozenset({"lisinopril", "spironolactone"}): (
        "high", "ACE inhibitor + K-sparing diuretic — hyperkalemia risk"
    ),
    frozenset({"simvastatin", "erythromycin"}): (
        "high", "Statin + macrolide — rhabdomyolysis risk"
    ),
    frozenset({"methotrexate", "trimethoprim"}): (
        "high", "Methotrexate + trimethoprim — bone marrow suppression"
    ),
}


class MedicationInteractionRetroSkill(Skill):
    def name(self) -> str:
        return "medication-interaction-retro"

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.EVENT

    def priority(self) -> Priority:
        return Priority.HIGH

    def event_filter(self) -> Optional[Dict[str, Any]]:
        return {"resource_type": "MedicationRequest"}

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "active_medications": DataRequirement(
                resource_type="MedicationRequest",
                filters={"status": "active"},
                time_window="4w",
                name="active_medications",
            ),
        }

    def response_schema(self) -> Optional[Dict[str, Any]]:
        return CLINICAL_RESPONSE_SCHEMA

    def max_reflections(self) -> int:
        return 2

    def goal(self) -> str:
        return "Detect dangerous drug-drug interactions among active medications"

    def build_prompt(self, ctx: AnalysisContext) -> str:
        meds = extract_records(ctx, "active_medications")
        lines = ["## Active Medication Data\n"]
        lines.append(f"Total active prescriptions: {len(meds)}")

        by_patient: Dict[str, List[str]] = {}
        for m in meds:
            pid = m.get("patient_id", m.get("subject", {}).get("reference", "unknown"))
            med = m.get("medication", m.get("medication_code", "unknown"))
            by_patient.setdefault(pid, []).append(str(med))

        for pid, med_list in sorted(by_patient.items()):
            lines.append(f"\n### Patient {pid}")
            for med in med_list:
                lines.append(f"- {med}")

        lines.append("\n### Analysis Required")
        lines.append("1. Check all medication pairs per patient for known interactions")
        lines.append("2. Identify multi-drug interaction chains (3+ drugs)")
        lines.append("3. Assess severity: contraindicated > major > moderate")
        lines.append("4. Consider cumulative risk for polypharmacy patients")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        meds = extract_records(ctx, "active_medications")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        by_patient: Dict[str, List[Dict[str, Any]]] = {}
        for m in meds:
            pid = m.get("patient_id", m.get("subject", {}).get("reference", ""))
            if pid:
                by_patient.setdefault(pid, []).append(m)

        for pid, patient_meds in by_patient.items():
            med_names = []
            for m in patient_meds:
                med = str(m.get("medication", m.get("medication_code", ""))).lower()
                med_names.append(med)

            for drug_a, drug_b in combinations(med_names, 2):
                pair = frozenset({drug_a, drug_b})
                if pair in _KNOWN_INTERACTIONS:
                    severity, reason = _KNOWN_INTERACTIONS[pair]
                    alerts.append(Alert(
                        skill_name=self.name(),
                        severity=severity,
                        category="medication-safety",
                        title=f"Drug interaction for patient {pid}: {drug_a} + {drug_b}",
                        description=reason,
                        patient_id=pid,
                        site_id=ctx.site_id,
                        evidence={
                            "patient_id": pid,
                            "drug_a": drug_a,
                            "drug_b": drug_b,
                            "reason": reason,
                        },
                        dedup_key=patient_dedup_key(self.name(), pid, now),
                        rule_validated=True,
                    ))

        return alerts

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        return critique_patient_findings(findings, ctx, "active_medications")
