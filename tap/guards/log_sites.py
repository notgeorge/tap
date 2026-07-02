"""Log-site token guards — `spec-tap-logging.md` (`req-tap-logging-site-id-scanner`).

Three distinct invariants over committed `logger.*` calls, split into three guards
(one invariant each):

- **format** — every site token is a bare 4-hex `[<hex>]` (no slug/prefix).
- **within-file uniqueness** — no hex is reused inside a single module.
- **baseline ratchet** — missing-token / convention-violation sites must equal
  `_log_site_id_baseline.txt` (currently empty ⇒ strict), ratcheting toward zero.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from tap.guards.base import REPO_ROOT, CeilingRatchet, Guard

if TYPE_CHECKING:
    from tap.logging import ScanResult, WellFormedSite
    from tap.source_scan import CallSite


def _scan() -> ScanResult:
    from tap.logging import scan_log_sites
    from tap.source_scan import first_party_source_roots

    return scan_log_sites(first_party_source_roots(REPO_ROOT))


def _key(site: CallSite | WellFormedSite) -> str:
    return f"{site.path.relative_to(REPO_ROOT)}:{site.lineno}"


class LogSiteFormatGuard(Guard):
    slug = "log-site-format"
    map_row = "Log-site tokens"
    description = (
        "A malformed site token ([<not-4-hex>]) breaks the structured-logging contract the future JSON "
        "formatter depends on. Every committed log call must open with a bare 4-hex [<hex>] token; this "
        "flags any that don't."
    )

    def check(self) -> None:
        malformed = _scan().malformed_ids
        assert not malformed, (
            "Malformed log-site token(s) — must be a bare 4-hex `[<hex>]` (e.g. `[a8f3]`), no slug or "
            "prefix. Mint one with `scripts/log-site-id`:\n  " + "\n  ".join(_key(s) for s in malformed)
        )


class LogSiteUniquenessGuard(Guard):
    slug = "log-site-within-file-uniqueness"
    map_row = "Log-site tokens"
    description = (
        "Two log calls sharing a hex within one module make a token ambiguous — you can't tell which "
        "call site a log line came from. Usually copy-paste. This flags any hex reused within a file."
    )

    def check(self) -> None:
        from tap.logging import find_within_file_duplicates

        dups = find_within_file_duplicates(_scan().well_formed)
        assert not dups, (
            "Duplicate log-site hex within a file (likely copy-paste) — regenerate one with "
            f"`scripts/log-site-id`:\n  {dups}"
        )


class LogSiteBaselineRatchet(CeilingRatchet):
    slug = "log-site-baseline"
    map_row = "Log-site tokens"
    description = (
        "A committed log call with no site token, or one violating the getLogger(__name__) convention, "
        "can't be traced to its callsite. The flagged set must equal the baseline (empty ⇒ strict) and "
        "ratchets toward zero, so new untokenized log calls can't accrete."
    )
    baseline_path: ClassVar[Path] = REPO_ROOT / "tap" / "tests" / "_log_site_id_baseline.txt"
    new_hint = "Add a bare 4-hex site token like `[a8f3]` to each new log call (mint it with " "`scripts/log-site-id`)."

    def measure(self) -> set[str]:
        result = _scan()
        current = {_key(s) for s in result.missing_ids}
        current |= {_key(site) for site, _reason in result.convention_violations}
        return current
