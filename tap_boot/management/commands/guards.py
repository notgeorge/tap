"""`manage.py guards` — print the development-time guard set (generated record).

PROTOTYPE of the "guards are the system of record" idea: enumerates every
registered `Guard` and prints what each declares about itself, so the Validation
Map can be *read off the code* rather than hand-maintained. `--check` runs each
guard and reports live pass/fail; `--json` emits machine-readable output.

Lives in tap_boot (the dev-validation gate's home, alongside `cold_boot_gate`).
It changes nothing — a read-only view over `tap.guards.report.build_report`.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from tap.guards.report import build_report


class Command(BaseCommand):
    help = "List the registered development-time guards (the generated Validation Map)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Run each guard's check() and report live pass/fail (slower: some fork pytest).",
        )
        parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
        parser.add_argument(
            "--sync-mypy",
            action="store_true",
            help="Regenerate the mypy ratchet baseline from the current `mypy .` state (reviewed changes only).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["sync_mypy"]:
            self._sync_mypy()
            return

        rows = build_report(run_checks=options["check"])

        if options["json"]:
            self.stdout.write(json.dumps([r.as_dict() for r in rows], indent=2))
            return

        self.stdout.write(f"{len(rows)} registered guard(s):\n")
        for row in rows:
            if row.passed is None:
                status = ""
            elif row.passed:
                status = self.style.SUCCESS("  PASS")
            else:
                status = self.style.ERROR("  FAIL")
            map_flag = "" if row.in_map else self.style.WARNING("  [not in Map]")
            self.stdout.write(f"• {row.slug}{status}{map_flag}")
            self.stdout.write(f"    map row: {row.map_row}")
            self.stdout.write(f"    module:  {row.module}")
            self.stdout.write(f"    why:     {row.description}")
            if row.error:
                self.stdout.write(self.style.ERROR(f"    error:   {row.error}"))
            self.stdout.write("")

    def _sync_mypy(self) -> None:
        """Regenerate the mypy ratchet baseline from the current `mypy .` state.

        Single source of the header + sort order the guard reads back, so a reviewed
        typing change re-baselines in one command instead of by hand.
        """
        from tap.guards.mypy import BASELINE_PATH, mypy_error_counts

        counts = mypy_error_counts()
        lines = sorted(f"{key}:{count}" for key, count in counts.items())
        header = [
            "# mypy strict-mode baseline (req-dev-validation-mypy-ratchet). One line per file+error-code:",
            "#   <path>:<error-code>:<count>",
            "# Frozen debt, mostly django-stubs friction + test no-untyped-call cascade (audited: not bugs).",
            "# A NEW error bumps a count -> ratchet fails. Regenerate ONLY for a reviewed change:",
            "#   manage.py guards --sync-mypy",
        ]
        BASELINE_PATH.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {len(lines)} baseline line(s), {sum(counts.values())} total mypy error(s).")
        )
