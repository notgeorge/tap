"""Authz-coverage ratchet — `req-tap-auth-policy-9` (the sink-heuristic half).

Every call to a privileged graph WRITE sink (`write_batch` / `grift_import` / a
`_*_internal` write helper) must sit inside a `@requires_capability` function or an
`authorized()` block. The scanner flags ungated sinks across the app surface (views,
endpoints, services); the flagged set must equal `baselines/authz.txt`, which
ratchets toward zero (currently empty/strict). The self-gating read executors are
deliberately excluded — see `tap/authz_coverage.py`. Sites are keyed by enclosing
scope (`path::qualname::sink`), not line number, so an ungated sink does not drift in
the baseline on unrelated edits. Complementary to the location-scoped service-gateway
guard (which has no heuristic and no baseline).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tap.guards.base import REPO_ROOT
from tap.guards.callsite import CallsiteRatchet, RemediationUnit, disambiguate
from tap.source_scan import CallSite, CallsiteIdentity


class AuthzCoverageRatchet(CallsiteRatchet):
    slug = "authz-coverage"
    map_row = "Authz coverage"
    rid = "req-tap-auth-policy-9"
    description = (
        "A call to a privileged graph write sink (write_batch / grift_import / a _*_internal write "
        "helper) outside a capability gate can mutate the graph without an authorization check. This "
        "flags every ungated sink and ratchets the baseline toward zero, so the per-app authZ build-out "
        "cannot regress and its remaining debt stays visible."
    )
    baseline_path: ClassVar[Path] = Path(__file__).resolve().parent / "baselines" / "authz.txt"
    #: Per-function: one gate clears every sink in the function, so the baseline keys
    #: on the anchor (two sinks in one function are one entry). The discriminator
    #: lives in the SARIF occurrence_key, never in the baseline.
    remediation_unit: ClassVar[RemediationUnit] = RemediationUnit.PER_ANCHOR
    new_hint = (
        "The call must sit inside a @requires_capability function or an authorized() block. Gate the "
        "enclosing function; if it is provably gated by a caller the per-function scanner cannot see, "
        "annotate the call `# TAP-AUTHZ-COV: <reason>`."
    )

    def collect(self) -> list[CallsiteIdentity]:
        from tap.authz_coverage import scan_authz_coverage
        from tap.source_scan import first_party_source_roots

        result = scan_authz_coverage(first_party_source_roots(REPO_ROOT))
        identities = [
            CallsiteIdentity(
                location=CallSite(s.path, s.lineno),
                anchor=s.key(REPO_ROOT),
                discriminator=s.discriminator(REPO_ROOT),
            )
            for s in result.ungated_sinks
        ]
        return disambiguate(identities)
