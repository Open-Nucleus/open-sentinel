"""Vital sign trend analysis skill."""

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

# LOINC codes
_SPO2_LOINC = "59408-5"
_HR_LOINC = "8867-4"
_RR_LOINC = "9279-1"
_TEMP_LOINC = "8310-5"
_BP_SYSTOLIC_LOINC = "8480-6"


class VitalSignTrendSkill(Skill):
    def name(self) -> str:
        return "vital-sign-trend"

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.EVENT

    def priority(self) -> Priority:
        return Priority.HIGH

    def event_filter(self) -> Optional[Dict[str, Any]]:
        return {"resource_type": "Observation"}

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "vitals": DataRequirement(
                resource_type="Observation",
                filters={
                    "code": (
                        f"{_SPO2_LOINC},{_HR_LOINC},{_RR_LOINC},"
                        f"{_TEMP_LOINC},{_BP_SYSTOLIC_LOINC}"
                    ),
                },
                time_window="24h",
                name="vitals",
            ),
        }

    def response_schema(self) -> Optional[Dict[str, Any]]:
        return CLINICAL_RESPONSE_SCHEMA

    def max_reflections(self) -> int:
        return 2

    def goal(self) -> str:
        return "Detect acute vital sign deterioration"

    def build_prompt(self, ctx: AnalysisContext) -> str:
        vitals = extract_records(ctx, "vitals")

        lines = ["## Vital Sign Data (24h)\n"]
        lines.append(f"Total observations: {len(vitals)}")

        by_patient: Dict[str, List[Dict[str, Any]]] = {}
        for v in vitals:
            pid = v.get("patient_id", v.get("subject", {}).get("reference", "unknown"))
            by_patient.setdefault(pid, []).append(v)

        for pid, obs in sorted(by_patient.items()):
            lines.append(f"\n### Patient {pid}")
            for o in obs:
                code = o.get("code", o.get("loinc", ""))
                value = o.get("value", "")
                ts = o.get("effective_date", o.get("effectiveDateTime", ""))
                lines.append(f"- {code}: {value} at {ts}")

        lines.append("\n### Analysis Required")
        lines.append("1. Evaluate each vital sign against thresholds")
        lines.append("2. Assess trend trajectory over 24h")
        lines.append("3. Score multiple concurrent abnormals")
        lines.append("4. Predict 6h deterioration risk")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        vitals = extract_records(ctx, "vitals")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        # Group by patient, keeping most extreme value per vital sign code
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
            if code in by_patient[pid]:
                # Keep worst value: lowest for SpO2, highest for others
                if code == _SPO2_LOINC:
                    by_patient[pid][code] = min(by_patient[pid][code], value)
                else:
                    by_patient[pid][code] = max(by_patient[pid][code], value)
            else:
                by_patient[pid][code] = value

        for pid, patient_vitals in by_patient.items():
            abnormals: List[str] = []
            max_severity = "moderate"

            spo2 = patient_vitals.get(_SPO2_LOINC)
            hr = patient_vitals.get(_HR_LOINC)
            rr = patient_vitals.get(_RR_LOINC)
            temp = patient_vitals.get(_TEMP_LOINC)

            if spo2 is not None and spo2 < 92:
                abnormals.append(f"SpO2 {spo2}%")
                max_severity = "high"

            if hr is not None and (hr > 120 or hr < 40):
                abnormals.append(f"HR {hr}")
                max_severity = "high"

            if rr is not None and rr > 30:
                abnormals.append(f"RR {rr}")
                max_severity = "high"

            if temp is not None:
                if temp > 40:
                    abnormals.append(f"Temp {temp}°C")
                    max_severity = "high"
                elif temp > 38.5:
                    abnormals.append(f"Temp {temp}°C")

            if not abnormals:
                continue

            if len(abnormals) >= 2:
                severity = "critical"
            else:
                severity = max_severity

            alerts.append(Alert(
                skill_name=self.name(),
                severity=severity,
                category="clinical-deterioration",
                title=f"Vital sign alert for patient {pid}: {', '.join(abnormals)}",
                description=(
                    f"Patient {pid} has {len(abnormals)} vital sign abnormality(ies): "
                    f"{', '.join(abnormals)}. Immediate clinical assessment recommended."
                ),
                patient_id=pid,
                site_id=ctx.site_id,
                evidence={
                    "patient_id": pid,
                    "abnormals": abnormals,
                    "spo2": spo2,
                    "heart_rate": hr,
                    "respiratory_rate": rr,
                    "temperature": temp,
                },
                measured_value=float(len(abnormals)),
                dedup_key=patient_dedup_key(self.name(), pid, now),
                rule_validated=True,
            ))

        return alerts

    def critique_findings(
        self, findings: List[Dict[str, Any]], ctx: AnalysisContext
    ) -> str:
        return critique_patient_findings(findings, ctx, "vitals")
