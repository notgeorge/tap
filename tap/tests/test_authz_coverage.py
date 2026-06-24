"""Authz-coverage scanner enforcement — `req-tap-auth-policy-9`.

The build-time dual of the stateless enforcement backstop: every call to a
privileged graph sink (`tap.authz_coverage.SINK_CALLS` — `write_batch`,
`grift_import`, the Search/Gryphon executors, the `_*_internal` write helpers)
must sit inside a `@requires_capability` function or an `authorized(...)` block,
else a privileged actor could reach the sink through a forgotten gate that the
runtime backstop (no ledger) cannot see.

Baseline ratchet — the set of ungated sink-call sites must equal the contents of
`_authz_coverage_baseline.txt`. A NEW entry fails the test (gate the call, or as
a last resort baseline it); a STALE entry fails too (a fix must remove its line),
so the baseline ratchets toward zero as the rest of the authZ build-out lands.
Mirrors `test_log_site_ids.py`. The scanner itself is in `tap.authz_coverage`.
"""

from __future__ import annotations

from pathlib import Path

from tap.authz_coverage import scan_authz_coverage
from tap.logging import CallSite, discover_scan_roots

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BASELINE_PATH = Path(__file__).resolve().parent / "_authz_coverage_baseline.txt"


def _key(site: CallSite) -> str:
    return f"{site.path.relative_to(_REPO_ROOT)}:{site.lineno}"


def _read_baseline() -> set[str]:
    if not _BASELINE_PATH.exists():
        return set()
    return {
        line.strip()
        for line in _BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_authz_coverage_ratchet() -> None:
    """Ungated privileged-sink calls must equal the baseline — new fail, stale fail."""
    result = scan_authz_coverage(discover_scan_roots(_REPO_ROOT))
    baseline = _read_baseline()
    current = {_key(s) for s in result.ungated_sinks}

    new_entries = sorted(current - baseline)
    stale_entries = sorted(baseline - current)

    messages: list[str] = []
    if new_entries:
        listing = "\n  ".join(new_entries)
        messages.append(
            f"New ungated privileged-sink calls not in baseline ({len(new_entries)}):\n  {listing}\n\n"
            "A call to write_batch / grift_import / a Search-Gryphon executor / a _*_internal write "
            "helper must sit inside a @requires_capability function or an authorized() block. Gate "
            "the enclosing function; if it is provably gated by a caller the per-function scanner "
            "cannot see, annotate the call `# noqa: TAP-AUTHZ-COV <reason>`. Only as a last resort "
            "append the entries to tap/tests/_authz_coverage_baseline.txt."
        )
    if stale_entries:
        listing = "\n  ".join(stale_entries)
        messages.append(
            f"Baseline entries no longer match any violation ({len(stale_entries)}):\n  {listing}\n\n"
            "These were fixed or moved — remove the lines from "
            "tap/tests/_authz_coverage_baseline.txt. The baseline ratchets toward zero."
        )

    if messages:
        raise AssertionError("\n\n".join(messages))
