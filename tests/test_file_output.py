"""Tests for FileOutput."""

import json

import pytest

from open_sentinel.outputs.file_output import FileOutput
from open_sentinel.testing.fixtures import make_alert


@pytest.fixture
def output_path(tmp_path):
    return str(tmp_path / "alerts.jsonl")


@pytest.fixture
def output(output_path):
    return FileOutput(path=output_path)


class TestFileOutputEmit:
    async def test_emit_creates_file(self, output, output_path):
        alert = make_alert(severity="high")
        result = await output.emit(alert)
        assert result is True
        with open(output_path) as f:
            lines = f.readlines()
        assert len(lines) == 1

    async def test_emit_json_lines_format(self, output, output_path):
        alert = make_alert(severity="high", title="Test Alert")
        await output.emit(alert)
        with open(output_path) as f:
            line = f.readline()
        data = json.loads(line)
        assert data["title"] == "Test Alert"
        assert data["severity"] == "high"
        assert data["requires_review"] is True

    async def test_emit_appends(self, output, output_path):
        await output.emit(make_alert(title="First"))
        await output.emit(make_alert(title="Second"))
        with open(output_path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["title"] == "First"
        assert json.loads(lines[1])["title"] == "Second"

    async def test_emit_returns_true(self, output):
        assert await output.emit(make_alert()) is True


class TestFileOutputAccepts:
    def test_accepts_all_by_default(self, output):
        assert output.accepts(make_alert(severity="low")) is True
        assert output.accepts(make_alert(severity="moderate")) is True
        assert output.accepts(make_alert(severity="high")) is True
        assert output.accepts(make_alert(severity="critical")) is True

    def test_min_severity_filter(self, output_path):
        output = FileOutput(path=output_path, min_severity="high")
        assert output.accepts(make_alert(severity="low")) is False
        assert output.accepts(make_alert(severity="moderate")) is False
        assert output.accepts(make_alert(severity="high")) is True
        assert output.accepts(make_alert(severity="critical")) is True

    def test_min_severity_critical(self, output_path):
        output = FileOutput(path=output_path, min_severity="critical")
        assert output.accepts(make_alert(severity="high")) is False
        assert output.accepts(make_alert(severity="critical")) is True


class TestFileOutputMeta:
    def test_name(self, output):
        assert output.name() == "file"
