"""Filename-convention scanner enforcement — `req-tap-json-scanner`.

Walks every TAP-owned `.json` file and asserts each conforms to the typed
filename convention (`req-tap-json-naming`) or is recorded in the baseline. New
non-conforming files fail; baselined entries pass; baseline entries that no
longer exist are reported as stale so the baseline ratchets toward empty.

The scanner itself lives in `tap.jsonfiles`; this file is the enforcement
surface, mirroring `tap/tests/test_log_site_ids.py`.
"""

from __future__ import annotations

from pathlib import Path

from tap.jsonfiles import DEFAULT_BASELINE, scan_json_files

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Source roots that hold TAP-owned JSON. Mirrors pyproject `testpaths` plus the
# app dirs whose config files this convention governs and the top-level `boot/`.
_ROOTS = [
    _REPO_ROOT / name
    for name in (
        "tap",
        "tap_grid",
        "tap_plugins",
        "tap_api",
        "tap_web",
        "tap_viz",
        "tap_ai",
        "tap_cares",
        "tap_auth",
        "tap_boot",
        "plugins",
        "boot",
    )
]


def test_json_filename_convention() -> None:
    """Every TAP-owned `.json` file is typed by its name, or is baselined."""
    result = scan_json_files(_ROOTS, baseline_path=DEFAULT_BASELINE)

    messages: list[str] = []
    if result.new_violations:
        listing = "\n  ".join(str(p) for p in result.new_violations)
        messages.append(
            f"JSON files whose names don't declare their purpose ({len(result.new_violations)}):\n  {listing}\n\n"
            "Name discovered data/config `<name>.<role>.json` (role in "
            f"{{boot, secret, grift, edge, gridkin}}), singleton app config "
            "`<app>.<name>.json`, and schemas `<type>.schema.json` "
            "(spec-tap-json-files.md req-tap-json-naming). If a file genuinely "
            "cannot be renamed now, append its repo-relative path to "
            "tap/tests/_json_file_baseline.txt — last resort only."
        )
    if result.stale_baseline:
        listing = "\n  ".join(result.stale_baseline)
        messages.append(
            f"Baseline entries that no longer exist ({len(result.stale_baseline)}):\n  {listing}\n\n"
            "Remove these lines from tap/tests/_json_file_baseline.txt — they "
            "have been renamed or deleted. The baseline ratchets down."
        )

    if messages:
        raise AssertionError("\n\n".join(messages))
