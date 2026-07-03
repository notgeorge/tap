"""Log-site baseline ratchet — `spec-tap-logging.md` (`req-tap-logging-site-id-scanner`).

Missing-token / convention-violation sites must equal the committed baseline
(currently empty ⇒ strict) and ratchet toward zero, so new untokenized log calls
cannot accrete.

Remediation is **per-call** (each violation is fixed by minting a token or fixing the
call), so this is a `CallsiteRatchet` at PER_OCCURRENCE granularity. A violation has
no `[<hex>]` yet, so it cannot use the well-formed `path::[<hex>]` anchor; its baseline
key is the drift-proof occurrence_key `path::qualname::<construct>::<kind>#<disc>`
(`spec-tap-callsite-identity`, `req-tap-callsite-identity-conformance`) — never
`path:lineno`, and never collapsed by a token-less `[<none>]`.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tap.guards._log_site_scan import scan
from tap.guards.base import REPO_ROOT
from tap.guards.callsite import CallsiteRatchet, RemediationUnit, disambiguate
from tap.source_scan import CallSite, CallsiteIdentity


class LogSiteBaselineRatchet(CallsiteRatchet):
    slug = "log-site-baseline"
    map_row = "Log-site tokens"
    rid = "req-tap-logging-site-id-scanner"
    description = (
        "A committed log call with no site token, or one violating the getLogger(__name__) convention, "
        "can't be traced to its callsite. The flagged set must equal the baseline (empty ⇒ strict) and "
        "ratchets toward zero, so new untokenized log calls can't accrete."
    )
    baseline_path: ClassVar[Path] = Path(__file__).resolve().parent / "baselines" / "log_site.txt"
    remediation_unit: ClassVar[RemediationUnit] = RemediationUnit.PER_OCCURRENCE
    new_hint = "Add a bare 4-hex site token like `[a8f3]` to each new log call (mint it with " "`scripts/log-site-id`)."

    def collect(self) -> list[CallsiteIdentity]:
        result = scan()
        sites = [*result.missing_ids, *result.convention_violations]
        identities = [
            CallsiteIdentity(
                location=CallSite(s.path, s.lineno),
                anchor=s.anchor(REPO_ROOT),
                discriminator=s.discriminator(REPO_ROOT),
            )
            for s in sites
        ]
        return disambiguate(identities)
