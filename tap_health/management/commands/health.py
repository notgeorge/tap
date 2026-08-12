"""`manage.py health` — the network-free health surface.

req-tap-health-exposure-2 / req-tap-health-selection (spec-tap-health-v0.md).
Runs `run_health()` in-process (actor-free) and prints the **full** projection
(the CLI is a trusted surface), so the spawn post-boot gate and container exec
readiness probes can branch on the exit code without a network endpoint.

`--set` is **required**: the caller states which question it is asking. There is
no default selection, because a default is invisible to the caller — a script or
an agent that inherits one cannot tell which probes ran, and the refusal message
teaches the vocabulary instead (accuracy over convenience).

  manage.py health --set readiness    # human-readable
  manage.py health --set readiness --json
  manage.py health --list-sets [--json]

Exit codes (distinct on purpose — a forgotten flag must not read as an outage):

  0  the selection ran and no critical probe is unhealthy
  1  a critical probe in the selection is unhealthy
  2  usage error (no `--set`, or an unknown selection name)
"""

from __future__ import annotations

import json
from typing import Any, NoReturn

from django.core.management.base import BaseCommand

from tap_health.registry import health_probe_registry
from tap_health.results import ProbeStatus
from tap_health.selection import SELECTION_NAMES, STANDARD_SELECTIONS, selects
from tap_health.service import run_health

EXIT_UNHEALTHY = 1
EXIT_USAGE = 2


class Command(BaseCommand):
    help = "Run a named set of instance health probes (exit 0 healthy / 1 unhealthy / 2 usage)."

    # Health must *report* broken state, not be preempted by it. Django runs the
    # system-check framework before handle() by default, and tap_cares registers
    # an untagged check that emits tap_cares.E001 on a required-for-boot malformed
    # secret — which would abort this command with a SystemCheckError instead of
    # the promised structured health JSON, exactly when health matters most. So
    # this command runs NO pre-command system checks; its own probes report the
    # broken state (the secrets probe surfaces that failure as unhealthy).
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: Any) -> None:
        # Deliberately neither argparse-`required` nor argparse-`choices`:
        # Django's CommandParser raises CommandError (exit 1) instead of exiting
        # 2 when a command is invoked programmatically via call_command, so
        # delegating validation to argparse would make the exit code depend on
        # HOW the command was called. Validating here keeps one code path, one
        # exit code (2), and one message — and lets the refusal explain what each
        # selection means rather than just listing names.
        parser.add_argument(
            "--set",
            dest="selection",
            help="Which selection set to run: " + ", ".join(SELECTION_NAMES),
        )
        parser.add_argument(
            "--list-sets",
            action="store_true",
            dest="list_sets",
            help="List the selection sets, their meaning, and their member probes.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit machine-readable JSON.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["list_sets"]:
            self._list_sets(as_json=options["as_json"])
            return

        selection = options["selection"]
        if not selection:
            self._usage_error("--set is required: name the health question to ask.")
        if selection not in SELECTION_NAMES:
            self._usage_error(f"Unknown selection {selection!r}.")

        report = run_health(selection=selection)
        if options["as_json"]:
            self.stdout.write(json.dumps(report.full(), indent=2, sort_keys=True))
        else:
            self._write_human(report)
        # Non-zero exit iff a critical probe is unhealthy (report.ok is False).
        if not report.ok:
            raise SystemExit(EXIT_UNHEALTHY)

    def _usage_error(self, message: str) -> NoReturn:
        """Refuse, naming every valid selection and what it means (exit 2)."""
        self.stderr.write(self.style.ERROR(message))
        for selection in STANDARD_SELECTIONS:
            self.stderr.write(f"  {selection.name}: {selection.description}")
        self.stderr.write("Run `manage.py health --list-sets [--json]` to see each set's member probes.")
        raise SystemExit(EXIT_USAGE)

    def _members(self, selection_name: str) -> list[dict[str, Any]]:
        """The probes that would run under `selection_name`, in report order."""
        probes = sorted(
            (health_probe_registry.get(name) for name in health_probe_registry.keys()),
            key=lambda p: (p.group, p.name),
        )
        return [
            {"name": p.name, "group": p.group, "critical": p.critical}
            for p in probes
            if selects(p.sets, selection_name)
        ]

    def _list_sets(self, *, as_json: bool) -> None:
        """Describe the selection vocabulary — the discovery affordance.

        Emitted machine-readably under `--json` so a programmatic caller learns
        the whole vocabulary (names, meanings, membership, criticality) in one
        call instead of guessing at it.
        """
        payload: list[dict[str, Any]] = [
            {
                "name": selection.name,
                "description": selection.description,
                "probes": self._members(selection.name),
            }
            for selection in STANDARD_SELECTIONS
        ]
        if as_json:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        for entry in payload:
            self.stdout.write(self.style.MIGRATE_HEADING(entry["name"]))
            self.stdout.write(f"  {entry['description']}")
            if not entry["probes"]:
                self.stdout.write("  (no probes)")
                continue
            for probe in entry["probes"]:
                crit = " (critical)" if probe["critical"] else ""
                self.stdout.write(f"  - [{probe['group']}] {probe['name']}{crit}")

    def _write_human(self, report: Any) -> None:
        overall = report.status.value
        styler = {
            ProbeStatus.HEALTHY.value: self.style.SUCCESS,
            ProbeStatus.DEGRADED.value: self.style.WARNING,
            ProbeStatus.UNHEALTHY.value: self.style.ERROR,
        }.get(overall, self.style.WARNING)
        self.stdout.write(styler(f"overall: {overall}  (selection: {report.selection})"))
        if not report.outcomes:
            self.stdout.write("  no probes are registered for this selection")
        for outcome in report.outcomes:
            r = outcome.result
            crit = " (critical)" if outcome.critical else ""
            line = f"  [{outcome.group}] {outcome.name}: {r.status.value}{crit}"
            if r.code:
                line += f"  code={r.code}"
            if r.detail:
                line += f"  — {r.detail}"
            self.stdout.write(line)
