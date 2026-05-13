"""Assert that every record_info / record_warn / record_error callsite in the
codebase uses a unique UUIDv7 in its `site` argument.

req-tap-cares-collector-job-model-15 (spec-tap-cares-collector.md).

The site UUID is the stable identifier of a callsite — what consumers grep
for in stored results to locate the exact line of source that emitted an
entry. Copy-pasting a record_* call without bumping the UUID would silently
collapse two callsites into one, defeating the locator. This test scans the
codebase for all record_* invocations and asserts no two share a site value.

It uses static text scanning (regex) rather than AST parsing on purpose:
fast, no Python import side-effects, robust to syntax errors in unrelated
files. The cost is that it requires the `site=...` literal to be either the
first positional argument or a keyword argument — which is the documented
calling convention anyway.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

# Project root: parent of `tap_cares/`.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories to skip when scanning. Test fixtures and the helper module
# itself intentionally contain repeated UUIDs / placeholder values.
_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "static",
    "build",
    "dist",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

# Files that are part of the testing/uniqueness machinery itself and use
# fake / repeated UUIDs by design.
_SKIP_FILES = {
    Path("tap_cares/tests/test_results_site_uniqueness.py"),
}

# UUIDv7 regex — matches the project's standard UUIDv7 format.
_UUIDV7 = r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"

# record_info|record_warn|record_error followed (eventually) by a quoted
# UUIDv7. Tolerates whitespace, newlines, intervening positional args.
# Matches the instance-method shape (`self.record_info("<uuid>", ...)`) and
# any legacy free-function form that lingers; either way the site UUID is
# the first quoted UUIDv7 inside the call.
_RECORD_CALL = re.compile(
    r"record_(?:info|warn|error)\s*\(" + r"[^)]*?" + r'["\'](' + _UUIDV7 + r')["\']',
    re.DOTALL,
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in _REPO_ROOT.rglob("*.py"):
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        rel = path.relative_to(_REPO_ROOT)
        if rel in _SKIP_FILES:
            continue
        files.append(path)
    return files


def test_record_callsite_uuids_are_unique():
    """No two record_* invocations in the codebase share the same site UUID."""
    seen: dict[str, list[tuple[Path, int]]] = defaultdict(list)

    for path in _iter_python_files():
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for match in _RECORD_CALL.finditer(text):
            uuid = match.group(1)
            line_no = text.count("\n", 0, match.start()) + 1
            seen[uuid].append((path.relative_to(_REPO_ROOT), line_no))

    duplicates = {uuid: sites for uuid, sites in seen.items() if len(sites) > 1}
    if duplicates:
        lines = ["Duplicate record_* site UUIDs found:"]
        for uuid, sites in sorted(duplicates.items()):
            lines.append(f"  {uuid}")
            for path, line_no in sites:
                lines.append(f"    {path}:{line_no}")
        lines.append("")
        lines.append(
            "Each record_info / record_warn / record_error callsite must use a "
            "unique UUIDv7. Generate fresh ones with `scripts/uuid7`."
        )
        pytest.fail("\n".join(lines))
