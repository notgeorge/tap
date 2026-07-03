"""Shared scan adapter for the three log-site guards (one invariant each).

Thin wrapper over the log-site scanner in `tap.logging`; the heavy AST work lives
there. The three guards (`log_site_format`, `log_site_uniqueness`,
`log_site_baseline`) import from here so each stays one-guard-per-file without
duplicating the scan call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tap.guards.base import REPO_ROOT

if TYPE_CHECKING:
    from tap.logging import ScanResult, WellFormedSite
    from tap.source_scan import CallSite


def scan() -> ScanResult:
    from tap.logging import scan_log_sites
    from tap.source_scan import first_party_source_roots

    return scan_log_sites(first_party_source_roots(REPO_ROOT))


def key(site: CallSite | WellFormedSite) -> str:
    return f"{site.path.relative_to(REPO_ROOT)}:{site.lineno}"
