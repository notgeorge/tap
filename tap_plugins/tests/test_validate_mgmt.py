"""Tests for the validate_plugin management command."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

PLUGINS_ROOT = Path(__file__).resolve().parent.parent.parent / "plugins"


@pytest.mark.django_db
class TestManagementCommand:
    def test_administrivia_structure_passes(self):
        out = StringIO()
        call_command("validate_plugin", str(PLUGINS_ROOT / "administrivia"), stdout=out)
        assert "PASS" in out.getvalue()

    def test_administrivia_loads_passes(self):
        out = StringIO()
        call_command("validate_plugin", str(PLUGINS_ROOT / "administrivia"), "--level", "loads", stdout=out)
        assert "PASS" in out.getvalue()

    def test_aws_core_runs_passes(self):
        out = StringIO()
        call_command("validate_plugin", str(PLUGINS_ROOT / "aws_core"), "--level", "runs", stdout=out)
        assert "PASS" in out.getvalue()

    def test_aws_core_json(self):
        out = StringIO()
        call_command("validate_plugin", str(PLUGINS_ROOT / "aws_core"), "--level", "runs", "--json", stdout=out)
        doc = json.loads(out.getvalue())
        assert doc["ok"] is True
        assert doc["level"] == "runs"

    def test_nonexistent_path_fails(self, tmp_path):
        with pytest.raises(CommandError, match="validation failed"):
            call_command("validate_plugin", str(tmp_path / "nope"))
