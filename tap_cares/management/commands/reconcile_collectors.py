"""Materialize the on-grid Collector node for every registered collector.

The explicit boot **population** step for collector nodes: app `ready()` registers
each collector runner in memory (read-only, req-plugin-load-v0-ready-readonly);
this command creates/updates the matching `Collector` grid node, run as the named
`tap_bootloader` actor — so no graph write happens before auth bootstrap exists.

`scripts/spawn-session.sh` calls this between `sync_auth` (which creates the
bootloader) and `fire_boot_collectors` (which needs the Collector nodes to exist).
Idempotent — safe to re-run on every boot. The future `tap_boot` population phase
absorbs this command (spec-tap-boot-v0).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from tap_auth.actors import BOOTLOADER, acting_as, get_builtin_actor
from tap_cares.registry import reconcile_collector_nodes


class Command(BaseCommand):
    help = "Materialize on-grid Collector nodes from the registry, as tap_bootloader."

    def handle(self, *args: Any, **options: Any) -> None:
        # This command is the interim boot orchestrator: IT sets the actor context,
        # and reconcile_collector_nodes() simply inherits it — tap_cares carries no
        # bootloader knowledge. The future tap_boot population phase takes this over.
        with acting_as(get_builtin_actor(BOOTLOADER)):
            summary = reconcile_collector_nodes()
        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciled collector nodes: {summary['created']} created, "
                f"{summary['updated']} updated, {summary['unchanged']} unchanged."
            )
        )
