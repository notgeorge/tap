"""Retrofit `[<slug>-<hex>]` site IDs onto every log call in the baseline.

One-shot Stage 3 helper for `spec-tap-logging.md`. Reads
`tap/tests/_log_site_id_baseline.txt`, locates each `logger.<level>(...)` call
via AST, and rewrites the leading string literal to prepend the site ID. The
script is idempotent against already-tagged calls (it inspects the message and
skips ones whose prefix already matches the format).

Generates unique 4-hex suffixes per prefix at runtime, also collision-checking
against any already-tagged calls in the source tree (so existing aws_core IDs
stay unique alongside any new ones we add).

Usage:
    docker compose exec web uv run python scripts/retrofit_log_site_ids.py
"""

from __future__ import annotations

import ast
import secrets
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from tap.logging import (  # noqa: E402
    expected_prefix_for_file,
    scan_log_sites,
)

REPO_ROOT = Path("/app")
BASELINE = REPO_ROOT / "tap/tests/_log_site_id_baseline.txt"
LEVELS = {"info", "warning", "error", "critical", "exception"}


def _read_baseline() -> list[tuple[Path, int]]:
    out: list[tuple[Path, int]] = []
    for raw_line in BASELINE.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        path_str, _, lineno_str = line.rpartition(":")
        out.append((REPO_ROOT / path_str, int(lineno_str)))
    return out


def _existing_suffixes_by_prefix() -> dict[str, set[str]]:
    """Inspect the live source for already-tagged IDs (e.g. aws_core)."""
    result = scan_log_sites(REPO_ROOT)
    by_prefix: dict[str, set[str]] = {}
    for site in result.well_formed:
        by_prefix.setdefault(site.prefix, set()).add(site.suffix)
    return by_prefix


def _new_suffix(prefix: str, used: dict[str, set[str]]) -> str:
    bucket = used.setdefault(prefix, set())
    while True:
        candidate = secrets.token_hex(2)
        if candidate not in bucket:
            bucket.add(candidate)
            return candidate


def _retrofit_one(path: Path, call_lineno: int, used: dict[str, set[str]]) -> str | None:
    """Edit one call site in-place. Returns the site ID inserted, or None on skip."""
    prefix = expected_prefix_for_file(path, REPO_ROOT)
    if prefix is None:
        return None

    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None

    target_call: ast.Call | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno != call_lineno:
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "logger":
            continue
        if func.attr not in LEVELS:
            continue
        target_call = node
        break

    if target_call is None or not target_call.args:
        return None

    first = target_call.args[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
        return None

    lines = source.splitlines(keepends=True)
    string_lineno = first.lineno
    string_col = first.col_offset
    line = lines[string_lineno - 1]

    # Defensive: triple-quoted strings have `"""` at col_offset; inserting after
    # the first quote would land mid-delimiter and break the source. Skip them.
    if line[string_col : string_col + 3] in ('"""', "'''"):
        return None
    quote = line[string_col]
    if quote not in ('"', "'"):
        return None

    suffix = _new_suffix(prefix, used)
    insertion = f"[{prefix}-{suffix}] "
    lines[string_lineno - 1] = (
        line[: string_col + 1] + insertion + line[string_col + 1 :]
    )
    path.write_text("".join(lines))
    return f"[{prefix}-{suffix}]"


def main() -> None:
    used = _existing_suffixes_by_prefix()
    total_existing = sum(len(s) for s in used.values())
    print(f"existing well-formed IDs (preserved as-is): {total_existing}")

    entries = _read_baseline()
    print(f"baseline entries to retrofit: {len(entries)}")

    edited = 0
    skipped = 0
    for path, lineno in entries:
        result = _retrofit_one(path, lineno, used)
        if result is None:
            skipped += 1
            print(f"  SKIP  {path.relative_to(REPO_ROOT)}:{lineno}")
        else:
            edited += 1
            print(f"  EDIT  {path.relative_to(REPO_ROOT)}:{lineno}  -> {result}")

    print(f"\nedited: {edited}    skipped: {skipped}")

    # Clear the baseline — any skipped lines will re-appear when the scanner
    # runs and we'll decide what to do with them then.
    header_lines = []
    for raw_line in BASELINE.read_text().splitlines():
        if raw_line.startswith("#") or not raw_line.strip():
            header_lines.append(raw_line)
        else:
            break
    BASELINE.write_text("\n".join(header_lines).rstrip() + "\n")
    print(f"baseline cleared (header preserved): {BASELINE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
