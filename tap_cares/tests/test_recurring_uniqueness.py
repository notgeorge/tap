"""Repository-wide check that exactly one `@recurring` task is declared.

req-tap-cares-task-backend-recurring-scope-4: Steady Queue's `@recurring`
decorator is used for **exactly one** task — the TAP scheduler tick.
Future scheduling needs always route through the on-grid `Schedule`
entity, never through new `@recurring` decorators.

Mirrors the `test_results_site_uniqueness.py` pattern: scan source files
for callsites of the regulated decorator and assert the expected count.
"""

from __future__ import annotations

from pathlib import Path

# Project root: tap_cares/tests/ → tap_cares/ → repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Directories to scan. Aligns with the testpaths set in pyproject.toml plus
# tap_cares itself (the recurring task lives in `tap_cares/task_backend.py`).
_SCAN_ROOTS = (
    "tap_cares",
    "tap_grid",
    "tap_plugins",
    "tap_api",
    "tap_web",
    "tap_viz",
    "plugins",
)


# The scanner file itself contains the string `@recurring(` in its docstrings
# and in the prefix it's checking for — exclude it so the enforcer doesn't
# count itself as a violator.
_SELF_RELATIVE = "tap_cares/tests/test_recurring_uniqueness.py"


def _iter_python_files() -> list[Path]:
    """Walk the project's Python source directories."""
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        root_path = _REPO_ROOT / root
        if not root_path.is_dir():
            continue
        files.extend(p for p in root_path.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def test_single_recurring_decoration() -> None:
    """Exactly one `@recurring(` decorator application exists in TAP source.

    The one permitted callsite is the TAP scheduler tick in
    `tap_cares/task_backend.py`. Any additional `@recurring` decorations
    violate `req-tap-cares-task-backend-recurring-scope-1` — schedule
    additions belong on the TAP grid as `Schedule` entities, not as
    code-level Steady Queue recurring tasks.

    Matches only lines whose stripped form begins with `@recurring(` —
    actual decorator applications, not text mentions inside docstrings or
    comments. The scanner file itself is excluded.
    """
    callsites: list[str] = []
    for path in _iter_python_files():
        if str(path.relative_to(_REPO_ROOT)) == _SELF_RELATIVE:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("@recurring("):
                callsites.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {stripped}")

    assert len(callsites) == 1, (
        f"Expected exactly one @recurring callsite (the TAP scheduler "
        f"tick in tap_cares/task_backend.py), found {len(callsites)}:\n  "
        + "\n  ".join(callsites)
        + "\n\nAdditional recurring tasks belong on the TAP grid as "
        "Schedule entities, not as @recurring decorators. See "
        "tap_cares/specs/spec-tap-cares-task-backend.md "
        "req-tap-cares-task-backend-recurring-scope-1."
    )

    # Sanity: the one callsite should be the scheduler tick declaration.
    assert "tap_cares/task_backend.py" in callsites[0], (
        f"Expected the @recurring callsite to live in "
        f"tap_cares/task_backend.py; got {callsites[0]}"
    )
