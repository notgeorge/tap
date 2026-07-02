"""Authz-coverage ratchet — `req-tap-auth-policy-9` (the sink-heuristic half).

Every call to a privileged graph sink (`write_batch` / `grift_import` / a
Search-Gryphon executor / a `_*_internal` write helper) must sit inside a
`@requires_capability` function or an `authorized()` block. The scanner flags
ungated sinks across the app surface (views, endpoints, services); the flagged set
must equal `_authz_coverage_baseline.txt`, which ratchets toward zero. Complementary
to the location-scoped service-gateway guard (which has no heuristic and no baseline).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tap.guards.base import REPO_ROOT, CeilingRatchet


class AuthzCoverageRatchet(CeilingRatchet):
    slug = "authz-coverage"
    map_row = "Authz coverage"
    description = (
        "A call to a privileged graph sink (write_batch / grift_import / a Search-Gryphon executor / "
        "a _*_internal write helper) outside a capability gate can mutate or read the graph without "
        "an authorization check. This flags every ungated sink and ratchets the baseline toward zero, "
        "so the per-app authZ build-out cannot regress and its remaining debt stays visible."
    )
    baseline_path: ClassVar[Path] = REPO_ROOT / "tap" / "tests" / "_authz_coverage_baseline.txt"
    new_hint = (
        "The call must sit inside a @requires_capability function or an authorized() block. Gate the "
        "enclosing function; if it is provably gated by a caller the per-function scanner cannot see, "
        "annotate the call `# TAP-AUTHZ-COV: <reason>`."
    )

    def measure(self) -> set[str]:
        from tap.authz_coverage import scan_authz_coverage
        from tap.logging import discover_scan_roots

        result = scan_authz_coverage(discover_scan_roots(REPO_ROOT))
        return {f"{s.path.relative_to(REPO_ROOT)}:{s.lineno}" for s in result.ungated_sinks}
