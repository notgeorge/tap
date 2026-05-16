"""Site-ID scanner enforcement — `req-tap-logging-site-id-scanner` (Option A).

Scans first-party apps and plugins for `logger.<level>(...)` calls and asserts:

* Format — site tokens are a bare `[<4 hex>]`, no slug/prefix
  (`req-tap-logging-site-id-scanner-3`, aligned with `req-tap-logging-site-ids-1`).
* Within-file uniqueness — no hex appears more than once among the well-formed
  tokens *in the same file*; the logger name (module path) namespaces the hex,
  so cross-file reuse is explicitly NOT a violation
  (`req-tap-logging-site-id-scanner-4`).
* Baseline ratchet — the set of missing-ID and convention-violation call sites
  must equal the contents of `_log_site_id_baseline.txt`; new entries fail the
  test, fixed entries become stale and must be removed
  (`req-tap-logging-site-id-scanner-5`, `-7`).

Option A removed the prior locality test: the callsite path is the derived
logger name (`__name__`), which a developer never authors, so there is nothing
for the scanner to validate about it. Mint fresh tokens with
`scripts/log-site-id`.

The scanner itself is in `tap.logging`. This file is the enforcement surface.
"""

from __future__ import annotations

from pathlib import Path

from tap.logging import (
    CallSite,
    ScanResult,
    WellFormedSite,
    discover_scan_roots,
    find_within_file_duplicates,
    scan_log_sites,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BASELINE_PATH = Path(__file__).resolve().parent / "_log_site_id_baseline.txt"


def _key(site: CallSite | WellFormedSite) -> str:
    return f"{site.path.relative_to(_REPO_ROOT)}:{site.lineno}"


def _scan() -> ScanResult:
    return scan_log_sites(discover_scan_roots(_REPO_ROOT))


def _read_baseline() -> set[str]:
    if not _BASELINE_PATH.exists():
        return set()
    return {
        line.strip()
        for line in _BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_no_malformed_site_ids() -> None:
    """Bracketed prefixes that don't match the bare 4-hex pattern are flagged."""
    result = _scan()
    if result.malformed_ids:
        lines = "\n  ".join(_key(s) for s in result.malformed_ids)
        raise AssertionError(
            f"Found {len(result.malformed_ids)} malformed site tokens:\n  {lines}\n\n"
            "Site tokens must be a bare 4-hex `[<hex>]` — e.g. `[a8f3]`. "
            "There is no slug or prefix (Option A). Mint one with "
            "`scripts/log-site-id`."
        )


def test_site_id_within_file_uniqueness() -> None:
    """No hex appears more than once among well-formed tokens in the same file.

    Cross-file reuse is allowed and intentionally not checked — the module
    path namespaces the hex (`req-tap-logging-site-id-scanner-4`).
    """
    result = _scan()
    duplicates = find_within_file_duplicates(result.well_formed)
    if duplicates:
        lines: list[str] = []
        for (path, hex_token), sites in sorted(
            duplicates.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
        ):
            rel = path.relative_to(_REPO_ROOT)
            linenos = ", ".join(str(s.lineno) for s in sites)
            lines.append(f"  {rel}: '{hex_token}' at lines {linenos}")
        raise AssertionError(
            f"Duplicate site hex within a file ({len(duplicates)} group(s)):\n"
            + "\n".join(lines)
            + "\n\nLikely copy-paste within the module — regenerate the hex at "
            "one of the call sites with `scripts/log-site-id`."
        )


def test_baseline_ratchet() -> None:
    """The missing-ID + convention-violation set must equal the baseline file.

    New entries (count grew) fail the test — add stable site tokens to the new
    log calls or, only if you must, append the entries to the baseline.
    Stale entries (count shrunk) also fail — remove them so the baseline
    keeps ratcheting toward zero.
    """
    result = _scan()
    baseline = _read_baseline()

    current: set[str] = set()
    for s in result.missing_ids:
        current.add(_key(s))
    for site, _reason in result.convention_violations:
        current.add(_key(site))

    new_entries = sorted(current - baseline)
    stale_entries = sorted(baseline - current)

    messages: list[str] = []
    if new_entries:
        listing = "\n  ".join(new_entries)
        messages.append(
            f"New log-site violations not in baseline ({len(new_entries)}):\n  {listing}\n\n"
            "Add a bare 4-hex site token like `[a8f3]` to each new log call "
            "(mint it with `scripts/log-site-id`). If you genuinely cannot fix "
            "these now, append the entries to tap/tests/_log_site_id_baseline.txt "
            "— but only as a last resort."
        )
    if stale_entries:
        listing = "\n  ".join(stale_entries)
        messages.append(
            f"Baseline entries no longer match any violation ({len(stale_entries)}):\n  {listing}\n\n"
            "Remove these lines from tap/tests/_log_site_id_baseline.txt — "
            "they have been fixed or the file has moved. The baseline ratchets down."
        )

    if messages:
        raise AssertionError("\n\n".join(messages))
