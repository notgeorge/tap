"""`manage.py health` — the network-free health surface.

req-tap-health-exposure-2 (spec-tap-health-v0.md). Runs `run_health()`
in-process (actor-free) and prints the **full** projection (the CLI is a
trusted surface). Exits non-zero when a critical probe is unhealthy, so the
spawn post-boot gate and container exec readiness probes can branch on it
without a network endpoint.

  manage.py health           # human-readable, exit 0/1
  manage.py health --json    # machine view (report.full()), exit 0/1
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from tap_health.results import ProbeStatus
from tap_health.service import run_health


class Command(BaseCommand):
    help = "Run the instance health probes and report status (exit non-zero on critical failure)."

    # Health must *report* broken state, not be preempted by it. Django runs the
    # system-check framework before handle() by default, and tap_cares registers
    # an untagged check that emits tap_cares.E001 on a required-for-boot malformed
    # secret — which would abort this command with a SystemCheckError instead of
    # the promised structured health JSON, exactly when health matters most. So
    # this command runs NO pre-command system checks; its own probes report the
    # broken state (the secrets probe surfaces that failure as unhealthy).
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit the full machine-readable report as JSON.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        report = run_health()
        if options["as_json"]:
            self.stdout.write(json.dumps(report.full(), indent=2, sort_keys=True))
        else:
            self._write_human(report)
        # Non-zero exit iff a critical probe is unhealthy (report.ok is False).
        if not report.ok:
            raise SystemExit(1)

    def _write_human(self, report: Any) -> None:
        overall = report.status.value
        styler = {
            ProbeStatus.HEALTHY.value: self.style.SUCCESS,
            ProbeStatus.DEGRADED.value: self.style.WARNING,
            ProbeStatus.UNHEALTHY.value: self.style.ERROR,
        }.get(overall, self.style.WARNING)
        self.stdout.write(styler(f"overall: {overall}"))
        for outcome in report.outcomes:
            r = outcome.result
            crit = " (critical)" if outcome.critical else ""
            line = f"  [{outcome.group}] {outcome.name}: {r.status.value}{crit}"
            if r.code:
                line += f"  code={r.code}"
            if r.detail:
                line += f"  — {r.detail}"
            self.stdout.write(line)
