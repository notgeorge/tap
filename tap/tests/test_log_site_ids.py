"""Site-ID scanner enforcement — `req-tap-logging-site-id-scanner`.

Scans first-party apps and plugins for `logger.<level>(...)` calls and asserts:

* Format — site IDs match `\\[<slug>-<4 hex>\\]` (`req-tap-logging-site-id-scanner-3`).
* Uniqueness — every (prefix, suffix) pair is globally unique
  (`req-tap-logging-site-id-scanner-4`).
* Locality — every site ID's prefix matches the slug of its containing app or
  plugin (`req-tap-logging-site-id-scanner-5`).
* Baseline ratchet — the set of missing-ID and convention-violation call sites
  must equal the contents of `_log_site_id_baseline.txt`; new entries fail
  the test, fixed entries become stale and must be removed
  (`req-tap-logging-site-id-scanner-6`, `-8`).

The scanner itself is in `tap.logging`. This file is the enforcement surface.
"""

from __future__ import annotations

from pathlib import Path

from tap.logging import (
    CallSite,
    WellFormedSite,
    find_duplicate_ids,
    find_locality_violations,
    scan_log_sites,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BASELINE_PATH = Path(__file__).resolve().parent / "_log_site_id_baseline.txt"


def _key(site: CallSite | WellFormedSite) -> str:
    return f"{site.path.relative_to(_REPO_ROOT)}:{site.lineno}"


def _read_baseline() -> set[str]:
    if not _BASELINE_PATH.exists():
        return set()
    return {
        line.strip()
        for line in _BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_no_malformed_site_ids() -> None:
    """Bracketed prefixes that don't match the canonical pattern are flagged."""
    result = scan_log_sites(_REPO_ROOT)
    if result.malformed_ids:
        lines = "\n  ".join(_key(s) for s in result.malformed_ids)
        raise AssertionError(
            f"Found {len(result.malformed_ids)} malformed site IDs:\n  {lines}\n\n"
            "Site IDs must match [<slug>-<4 hex>] — e.g. [tap_cares-a8f3]."
        )


def test_site_id_uniqueness() -> None:
    """Every (prefix, suffix) pair appears at most once across the codebase."""
    result = scan_log_sites(_REPO_ROOT)
    duplicates = find_duplicate_ids(result.well_formed)
    if duplicates:
        lines: list[str] = []
        for (prefix, suffix), sites in sorted(duplicates.items()):
            site_list = ", ".join(_key(s) for s in sites)
            lines.append(f"  [{prefix}-{suffix}]: {site_list}")
        raise AssertionError(
            f"Duplicate site IDs found ({len(duplicates)} group(s)):\n"
            + "\n".join(lines)
            + "\n\nLikely copy-paste — regenerate the suffix at one of the call sites."
        )


def test_site_id_locality() -> None:
    """Every site ID's prefix matches the containing app or plugin slug."""
    result = scan_log_sites(_REPO_ROOT)
    violations = find_locality_violations(result.well_formed, _REPO_ROOT)
    if violations:
        lines = "\n  ".join(f"{_key(site)}: {reason}" for site, reason in violations)
        raise AssertionError(
            f"Site-ID locality violations ({len(violations)}):\n  {lines}\n\n"
            "The prefix in each ID must match the slug of the file's containing "
            "app (tap_*) or plugin (plugins/<slug>/)."
        )


def test_baseline_ratchet() -> None:
    """The missing-ID + convention-violation set must equal the baseline file.

    New entries (count grew) fail the test — add stable site IDs to the new
    log calls or, only if you must, append the entries to the baseline.
    Stale entries (count shrunk) also fail — remove them so the baseline
    keeps ratcheting toward zero.
    """
    result = scan_log_sites(_REPO_ROOT)
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
            "Add a stable site ID like `[<slug>-<hex>]` to each new log call "
            "(generate the hex via `python -c \"import secrets; print(secrets.token_hex(2))\"`). "
            "If you genuinely cannot fix these now, append the entries to "
            "tap/tests/_log_site_id_baseline.txt — but only as a last resort."
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
