"""Log-site baseline ratchet — `spec-tap-logging.md` (`req-tap-logging-site-id-scanner`).

Missing-token / convention-violation sites must equal the committed baseline
(currently empty ⇒ strict) and ratchet toward zero, so new untokenized log calls
cannot accrete.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tap.guards._log_site_scan import key, scan
from tap.guards.base import CeilingRatchet


class LogSiteBaselineRatchet(CeilingRatchet):
    slug = "log-site-baseline"
    map_row = "Log-site tokens"
    rid = "req-tap-logging-site-id-scanner"
    description = (
        "A committed log call with no site token, or one violating the getLogger(__name__) convention, "
        "can't be traced to its callsite. The flagged set must equal the baseline (empty ⇒ strict) and "
        "ratchets toward zero, so new untokenized log calls can't accrete."
    )
    baseline_path: ClassVar[Path] = Path(__file__).resolve().parent / "baselines" / "log_site.txt"
    new_hint = (
        "Add a bare 4-hex site token like `[a8f3]` to each new log call (mint it with "
        "`scripts/log-site-id`)."
    )

    def measure(self) -> set[str]:
        result = scan()
        current = {key(s) for s in result.missing_ids}
        current |= {key(site) for site, _reason in result.convention_violations}
        return current
