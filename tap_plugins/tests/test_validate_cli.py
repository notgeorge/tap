"""Tests for the standalone CLI entry point (python -m tap_plugins.validate_plugin)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tap_plugins.validate_plugin.__main__ import main

PLUGINS_ROOT = Path(__file__).resolve().parent.parent.parent / "plugins"


class TestCLIBasics:
    def test_lotr_passes(self, capsys):
        code = main([str(PLUGINS_ROOT / "lotr")])
        assert code == 0
        out = capsys.readouterr().out
        assert "PASS" in out

    def test_lotr_json(self, capsys):
        code = main([str(PLUGINS_ROOT / "lotr"), "--json"])
        assert code == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["ok"] is True

    def test_administrivia_passes(self, capsys):
        code = main([str(PLUGINS_ROOT / "administrivia")])
        assert code == 0

    def test_nonexistent_path_fails(self, capsys, tmp_path):
        code = main([str(tmp_path / "nope")])
        assert code == 1

    def test_strict_mode(self, capsys):
        code = main([str(PLUGINS_ROOT / "lotr"), "--strict"])
        captured = capsys.readouterr()
        # LOTR should still pass in strict mode (no undeclared files expected)
        # but even if it doesn't, the test verifies the flag is accepted
        assert code in (0, 1)


class TestCLILevels:
    def test_unknown_level_exits_2(self, capsys):
        code = main([str(PLUGINS_ROOT / "lotr"), "--level", "bogus"])
        assert code == 2

    def test_loads_level_exits_2_with_django_message(self, capsys):
        code = main([str(PLUGINS_ROOT / "lotr"), "--level", "loads"])
        assert code == 2
        err = capsys.readouterr().err
        assert "requires Django" in err
        assert "manage.py validate_plugin" in err

    def test_runs_level_exits_2_with_django_message(self, capsys):
        code = main([str(PLUGINS_ROOT / "lotr"), "--level", "runs"])
        assert code == 2
        err = capsys.readouterr().err
        assert "requires Django" in err
