"""Source-control leak-guard enforcement — `req-tap-cares-secrets-leak-guard`.

Push-protection beyond `.gitignore`: a real secret must never enter the repo,
whether as a `*.secret.json` (ignore bypassed via `git add -f`) or renamed to
dodge the suffix. The scan logic lives in `tap.runtime_secrets`; this file is the
enforcement surface, mirroring `tap/tests/test_json_files.py` and
`tap/tests/test_log_site_ids.py` (a filesystem walk, no git dependency, so it
runs in-container like the sibling scanners).

The repo-wide test walks the tree for `*.json`, excluding vendored/cache dirs and
the live secrets mount (`tap_secrets`, gitignored and symlinked out of the tree).
The unit tests pin the scan logic.
"""

from __future__ import annotations

import json
from pathlib import Path

from tap.runtime_secrets import scan_paths_for_secret_leaks

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Dirs never walked: vendored/cache trees plus `tap_secrets`, the live off-grid
# secrets mount (a gitignored symlink to the host store). Mirrors the exclusion
# discipline in `tap/jsonfiles.py`.
_EXCLUDE_DIRS = frozenset(
    {".venv", "node_modules", "__pycache__", ".git", ".claude", ".mypy_cache", ".pytest_cache", "vendor", "tap_secrets"}
)


def _repo_json_files() -> list[str]:
    """Repo-relative `.json` files in the tree, excluding the mount + vendored dirs."""
    rels: list[str] = []
    for path in _REPO_ROOT.rglob("*.json"):
        if any(part in _EXCLUDE_DIRS for part in path.relative_to(_REPO_ROOT).parts):
            continue
        if path.is_file():
            rels.append(str(path.relative_to(_REPO_ROOT)))
    return rels


def test_no_secret_material_in_repo_tree() -> None:
    """No file in the tree is a `*.secret.json` or a disguised secret envelope."""
    leaks = scan_paths_for_secret_leaks(_REPO_ROOT, _repo_json_files())
    if leaks:
        listing = "\n  ".join(f"{leak.path} — {leak.reason}" for leak in leaks)
        raise AssertionError(
            f"Secret material found in the repository tree ({len(leaks)}):\n  {listing}\n\n"
            "Secrets live only in the mounted *.secret.json store (off-grid, gitignored). "
            "Remove the file (and rotate the credential — treat it as compromised). A "
            "non-secret placeholder may use the *.secret.example.json suffix "
            "(spec-tap-cares-secrets.md req-tap-cares-secrets-leak-guard)."
        )


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
