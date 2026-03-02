"""Tests for FhirFlagOutput."""

import json

import pytest

from open_sentinel.outputs.fhir_flag import FhirFlagOutput
from open_sentinel.testing.fixtures import make_alert


@pytest.fixture
def output_dir(tmp_path):
    return str(tmp_path / "fhir_output")


@pytest.fixture
def output(output_dir):
    return FhirFlagOutput(output_dir=output_dir)


class TestFhirFlagOutputEmit:
    async def test_emit_creates_file(self, output, output_dir):
        alert = make_alert(severity="high", title="Test FHIR")
        result = await output.emit(alert)
        assert result is True

        import os
        files = os.listdir(output_dir)
        assert len(files) == 1
        assert files[0].startswith("detected-issue-")
        assert files[0].endswith(".json")

    async def test_emit_valid_fhir_json(self, output, output_dir):
        alert = make_alert(severity="high", title="Test FHIR")
        await output.emit(alert)

        import os
        files = os.listdir(output_dir)
        filepath = os.path.join(output_dir, files[0])
        with open(filepath) as f:
            data = json.load(f)

        assert data["resourceType"] == "DetectedIssue"
        assert data["status"] == "preliminary"
        assert data["severity"] == "high"
        assert "extension" in data

    async def test_emit_fhir_severity_mapping(self, output, output_dir):
        # critical maps to "high" in FHIR
        alert = make_alert(severity="critical")
        await output.emit(alert)

        import os
        files = os.listdir(output_dir)
        filepath = os.path.join(output_dir, files[0])
        with open(filepath) as f:
            data = json.load(f)
        assert data["severity"] == "high"

    async def test_emit_moderate_severity(self, output, output_dir):
        alert = make_alert(severity="moderate")
        await output.emit(alert)

        import os
        files = os.listdir(output_dir)
        filepath = os.path.join(output_dir, files[0])
        with open(filepath) as f:
            data = json.load(f)
        assert data["severity"] == "moderate"

    async def test_emit_with_patient_reference(self, output, output_dir):
        alert = make_alert(severity="high", patient_id="patient-123")
        await output.emit(alert)

        import os
        files = os.listdir(output_dir)
        filepath = os.path.join(output_dir, files[0])
        with open(filepath) as f:
            data = json.load(f)
        assert data["patient"]["reference"] == "Patient/patient-123"

    async def test_emit_ai_provenance_extensions(self, output, output_dir):
        alert = make_alert(
            severity="high",
            ai_generated=True,
            ai_confidence=0.85,
        )
        await output.emit(alert)

        import os
        files = os.listdir(output_dir)
        filepath = os.path.join(output_dir, files[0])
        with open(filepath) as f:
            data = json.load(f)

        extensions = data["extension"]
        ext_urls = {e["url"] for e in extensions}
        assert "http://open-sentinel.org/fhir/ai-generated" in ext_urls
        assert "http://open-sentinel.org/fhir/ai-confidence" in ext_urls
        assert "http://open-sentinel.org/fhir/requires-review" in ext_urls

        # Find the ai-generated extension
        ai_gen = next(e for e in extensions if "ai-generated" in e["url"])
        assert ai_gen["valueBoolean"] is True

        # Find requires-review extension
        review = next(e for e in extensions if "requires-review" in e["url"])
        assert review["valueBoolean"] is True

    async def test_emit_multiple_files(self, output, output_dir):
        await output.emit(make_alert(severity="high", title="First"))
        await output.emit(make_alert(severity="critical", title="Second"))

        import os
        files = os.listdir(output_dir)
        assert len(files) == 2


class TestFhirFlagOutputAccepts:
    def test_accepts_all_by_default(self, output):
        assert output.accepts(make_alert(severity="low")) is True
        assert output.accepts(make_alert(severity="moderate")) is True
        assert output.accepts(make_alert(severity="high")) is True
        assert output.accepts(make_alert(severity="critical")) is True

    def test_min_severity_filter(self, output_dir):
        output = FhirFlagOutput(output_dir=output_dir, min_severity="high")
        assert output.accepts(make_alert(severity="low")) is False
        assert output.accepts(make_alert(severity="moderate")) is False
        assert output.accepts(make_alert(severity="high")) is True
        assert output.accepts(make_alert(severity="critical")) is True


class TestFhirFlagOutputMeta:
    def test_name(self, output):
        assert output.name() == "fhir-flag"
