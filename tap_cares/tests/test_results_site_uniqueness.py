"""Assert that record_* site tokens are unique *within each file*.

req-tap-cares-collector-job-model-15 (spec-tap-cares-collector.md), aligned
with req-tap-logging-site-id-scanner-4 (spec-tap-logging.md).

Under the unified message object (Option A), `site` is a 4-hex token, not a
UUIDv7, and the unique callsite *path* is the logger/module — so the hex only
has to be unique **within its file**. Copy-pasting a record_* call (or its
`_SITE_*` constant) within a file without bumping the hex would collapse two
callsites into one; copy-pasting *across* files is inherently safe because the
file namespaces the hex, and is explicitly NOT a violation.

Collectors define their site tokens as module constants
(`_SITE_RUN_STARTED = "7f18"`) and pass the constant to the call. So the
realistic failure mode is two `_SITE_*` constants in one file sharing a hex,
plus any inline-literal first argument to a record_* call. This scans for
both, per file.

Static text scanning (regex) on purpose: fast, no import side-effects, robust
to unrelated syntax errors. Mint fresh tokens with `scripts/log-site-id`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

# Project root: parent of `tap_cares/`.
_REPO_ROOT = Path(__file__).resolve().parents[2]

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

# This scanner module itself uses example hexes in its docstring.
_SKIP_FILES = {
    Path("tap_cares/tests/test_results_site_uniqueness.py"),
}

_HEX = r"[0-9a-f]{4}"

# A `_SITE_<NAME> = "<hex>"` module/class constant assignment.
_SITE_CONST = re.compile(r"^\s*_SITE_[A-Z0-9_]+\s*=\s*[\"'](" + _HEX + r")[\"']\s*$", re.MULTILINE)

# An inline first-positional string literal to a record_* call:
# `record_info("7f18", ...)`. Constant-based calls are covered by _SITE_CONST.
_RECORD_INLINE = re.compile(
    r"record_(?:info|warn|error)\s*\(\s*[\"'](" + _HEX + r")[\"']",
    re.DOTALL,
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in _REPO_ROOT.rglob("*.py"):
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.relative_to(_REPO_ROOT) in _SKIP_FILES:
            continue
        files.append(path)
    return files


def test_record_site_tokens_unique_within_file():
    """No file defines/uses the same record_* site hex twice.

    Cross-file reuse is allowed and intentionally not checked — the module
    path namespaces the hex (req-tap-logging-site-id-scanner-4).
    """
    offenders: list[str] = []

    for path in _iter_python_files():
        try:
            text = path.read_text()
        except OSError, UnicodeDecodeError:
            continue

        seen: dict[str, list[int]] = defaultdict(list)
        for match in _SITE_CONST.finditer(text):
            seen[match.group(1)].append(text.count("\n", 0, match.start()) + 1)
        for match in _RECORD_INLINE.finditer(text):
            seen[match.group(1)].append(text.count("\n", 0, match.start()) + 1)

        rel = path.relative_to(_REPO_ROOT)
        for hex_tok, lines in sorted(seen.items()):
            if len(lines) > 1:
                offenders.append(f"  {rel}: '{hex_tok}' at lines {sorted(lines)}")

    if offenders:
        pytest.fail(
            "Duplicate record_* site hex within a file:\n"
            + "\n".join(offenders)
            + "\n\nEach site token must be unique within its file. "
            "Mint fresh ones with `scripts/log-site-id`."
        )
