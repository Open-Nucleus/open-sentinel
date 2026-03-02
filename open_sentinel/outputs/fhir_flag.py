"""FHIR DetectedIssue R4 output: writes alerts as FHIR JSON files."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

from open_sentinel.interfaces import AlertOutput
from open_sentinel.types import Alert

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"low": 1, "moderate": 2, "high": 3, "critical": 4}

_FHIR_SEVERITY_MAP = {
    "critical": "high",
    "high": "high",
    "moderate": "moderate",
    "low": "low",
}


class FhirFlagOutput(AlertOutput):
    def __init__(self, output_dir: str, min_severity: str = "low"):
        self._output_dir = Path(output_dir)
        self._min_severity = min_severity

    def name(self) -> str:
        return "fhir-flag"

    def accepts(self, alert: Alert) -> bool:
        alert_level = _SEVERITY_ORDER.get(alert.severity, 0)
        min_level = _SEVERITY_ORDER.get(self._min_severity, 1)
        return alert_level >= min_level

    def _to_fhir(self, alert: Alert) -> Dict[str, Any]:
        resource: Dict[str, Any] = {
            "resourceType": "DetectedIssue",
            "id": alert.id,
            "status": "preliminary",
            "severity": _FHIR_SEVERITY_MAP.get(alert.severity, "moderate"),
            "detail": alert.description or alert.title,
        }

        if alert.fhir_code:
            resource["code"] = {
                "coding": [{"system": "http://snomed.info/sct", "code": alert.fhir_code}],
                "text": alert.title,
            }

        if alert.patient_id:
            resource["patient"] = {"reference": f"Patient/{alert.patient_id}"}

        extensions = []
        extensions.append({
            "url": "http://open-sentinel.org/fhir/ai-generated",
            "valueBoolean": alert.ai_generated,
        })
        if alert.ai_model:
            extensions.append({
                "url": "http://open-sentinel.org/fhir/ai-model",
                "valueString": alert.ai_model,
            })
        if alert.ai_confidence is not None:
            extensions.append({
                "url": "http://open-sentinel.org/fhir/ai-confidence",
                "valueDecimal": alert.ai_confidence,
            })
        extensions.append({
            "url": "http://open-sentinel.org/fhir/reflection-iterations",
            "valueInteger": alert.reflection_iterations,
        })
        extensions.append({
            "url": "http://open-sentinel.org/fhir/rule-validated",
            "valueBoolean": alert.rule_validated,
        })
        extensions.append({
            "url": "http://open-sentinel.org/fhir/requires-review",
            "valueBoolean": alert.requires_review,
        })
        resource["extension"] = extensions

        if alert.evidence:
            resource["evidence"] = [{"detail": [{"text": json.dumps(alert.evidence)}]}]

        return resource

    def _write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    async def emit(self, alert: Alert) -> bool:
        fhir = self._to_fhir(alert)
        content = json.dumps(fhir, indent=2)
        filename = f"detected-issue-{alert.id}.json"
        filepath = self._output_dir / filename
        try:
            await asyncio.to_thread(self._write_file, filepath, content)
            return True
        except Exception:
            logger.exception("FHIR flag write failed for %s", alert.id)
            return False
