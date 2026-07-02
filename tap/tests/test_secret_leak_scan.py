"""Pure-scan unit coverage for the secret-leak scanner — `req-tap-cares-secrets-leak-guard`.

The scan logic lives in `tap.runtime_secrets`; these tests pin its behaviour over
synthetic tracked paths. The repo-wide enforcement walk (a filesystem scan of the
whole tree) is `tap/guards/secrets.py::SecretLeakGuard`, run via
`tap/tests/test_guards.py` — this file keeps only the fast, DB-free unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from tap.runtime_secrets import scan_paths_for_secret_leaks


class TestScanLogic:
    """Unit coverage of the pure scan function over synthetic tracked paths."""

    def _envelope(self) -> dict:
        return {
            "scope": "auth",
            "key": "criticalsec-google",
            "kind": "oidc_client",
            "description": "x",
            "data": {"client_id": "a", "client_secret": "b"},
        }

    def test_committed_secret_json_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "leaked.secret.json").write_text(json.dumps(self._envelope()), encoding="utf-8")
        leaks = scan_paths_for_secret_leaks(tmp_path, ["leaked.secret.json"])
        assert [leak.path for leak in leaks] == ["leaked.secret.json"]
        assert "*.secret.json" in leaks[0].reason

    def test_disguised_envelope_flagged(self, tmp_path: Path) -> None:
        # Real secret renamed to dodge the .secret.json suffix.
        (tmp_path / "config.json").write_text(json.dumps(self._envelope()), encoding="utf-8")
        leaks = scan_paths_for_secret_leaks(tmp_path, ["config.json"])
        assert [leak.path for leak in leaks] == ["config.json"]
        assert "envelope" in leaks[0].reason

    def test_example_template_allowed(self, tmp_path: Path) -> None:
        (tmp_path / "google.secret.example.json").write_text(json.dumps(self._envelope()), encoding="utf-8")
        assert scan_paths_for_secret_leaks(tmp_path, ["google.secret.example.json"]) == []

    def test_test_fixture_envelope_allowed(self, tmp_path: Path) -> None:
        fixture = tmp_path / "tap_cares" / "tests" / "fixtures" / "sample.json"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(json.dumps(self._envelope()), encoding="utf-8")
        rel = "tap_cares/tests/fixtures/sample.json"
        assert scan_paths_for_secret_leaks(tmp_path, [rel]) == []

    def test_ordinary_json_not_flagged(self, tmp_path: Path) -> None:
        # A boot-profile-shaped doc has none of the envelope's four fields.
        (tmp_path / "base.boot.json").write_text(
            json.dumps({"profile_id": "base", "version": 1, "population": {"steps": []}}),
            encoding="utf-8",
        )
        assert scan_paths_for_secret_leaks(tmp_path, ["base.boot.json"]) == []

    def test_schema_file_not_flagged(self, tmp_path: Path) -> None:
        # A schema describes the envelope but does not instantiate its fields.
        (tmp_path / "oidc.schema.json").write_text(
            json.dumps({"type": "object", "properties": {"scope": {"type": "string"}}}),
            encoding="utf-8",
        )
        assert scan_paths_for_secret_leaks(tmp_path, ["oidc.schema.json"]) == []

    def test_unparseable_json_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        assert scan_paths_for_secret_leaks(tmp_path, ["broken.json"]) == []
