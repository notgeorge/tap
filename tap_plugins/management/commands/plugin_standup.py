"""Generic plugin standup runner — the non-grid sibling of import_plugin_grift.

Implements `req-plugin-load-v0-standup-hook` (spec-plugin-load-lifecycle-v0.md):
invokes each plugin's standup hook in INSTALLED_APPS order, where `grift`
seeds the grid and `standup` prepares non-grid capabilities a plugin's
collectors need. Discovery convention: a plugin's standup hook is a
plugin-owned management command named `<app_label>_standup`. Plugins with
no such command are skipped. This runner is plugin-agnostic — the only
core surface of the seam.

Usage (post-migrate stand-up step, sibling to `import_plugin_grift --all`):
    manage.py plugin_standup --all
    manage.py plugin_standup aws_core
"""

from __future__ import annotations

from django.apps import apps
from django.core.management import call_command, get_commands
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run plugin standup hooks (<app_label>_standup) in INSTALLED_APPS order."

    def add_arguments(self, parser) -> None:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--all", action="store_true", default=False, help="Run every plugin's standup hook.")
        group.add_argument("app_label", nargs="?", help="Run only this app's standup hook.")
        parser.add_argument("--force", action="store_true", default=False, help="Forwarded to each standup hook.")

    def handle(self, *args, **options) -> None:
        run_all: bool = options["all"]
        only: str | None = options.get("app_label")
        force: bool = options["force"]

        commands = get_commands()  # {command_name: app_name}

        labels = [ac.label for ac in apps.get_app_configs()]
        if only is not None:
            if only not in labels:
                raise CommandError(f"Unknown app label {only!r}. Known: {', '.join(labels)}")
            labels = [only]

        ran: list[str] = []
        skipped: list[str] = []
        for label in labels:
            cmd = f"{label}_standup"
            if cmd not in commands:
                skipped.append(label)
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(f"==> {label}: {cmd}"))
            call_command(cmd, *(["--force"] if force else []))
            ran.append(label)

        if only is None and run_all:
            self.stdout.write(
                self.style.SUCCESS(f"plugin_standup: ran {ran or '[]'}; no hook for {len(skipped)} app(s).")
            )
        elif not ran:
            raise CommandError(f"{only!r} has no standup hook ({only}_standup not registered).")
