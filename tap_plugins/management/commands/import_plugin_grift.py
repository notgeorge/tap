"""Import bundled GRIFT data for one or more TAP plugins.

Usage:
    docker compose exec web uv run python manage.py import_plugin_grift lotr
    docker compose exec web uv run python manage.py import_plugin_grift lotr --bundle core-data
    docker compose exec web uv run python manage.py import_plugin_grift --all

Reads each plugin's tap-plugin.toml manifest, finds declared [[grift]] bundles,
and calls grift_import on each one using strict upsert semantics.
"""

from __future__ import annotations

import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from tap_plugins.base import TapPluginConfig


class Command(BaseCommand):
    help = "Import declared GRIFT bundles for one or more TAP plugins."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "plugin_slugs",
            nargs="*",
            metavar="PLUGIN_SLUG",
            help="One or more plugin slugs to import (e.g. lotr).",
        )
        group.add_argument(
            "--all",
            dest="all_plugins",
            action="store_true",
            default=False,
            help="Import GRIFT data for all registered TAP plugins.",
        )
        parser.add_argument(
            "--bundle",
            dest="bundle_name",
            default=None,
            help="Import only this named bundle (applies to all specified plugins).",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            default=False,
            help="Parse and validate GRIFT files without writing to the database.",
        )
        parser.add_argument(
            "--force-batches",
            dest="force_batches",
            default="",
            help=(
                "Comma-separated list of batch_entity_id UUIDs to force re-import. "
                "Bypasses the skip-if-exists guard for the named batches only. "
                "Permitted if and only if DEBUG=True. See req-grid-import-grift-force-reimport."
            ),
        )
        parser.add_argument(
            "--sweep-strict",
            dest="sweep_strict",
            action="store_true",
            default=False,
            help=(
                "With --force-batches, abort the run before any writes if any "
                "sweep candidate fails a guardrail. See req-grid-import-grift-batch-scoped-sweep."
            ),
        )
        parser.add_argument(
            "--purge",
            dest="purge",
            action="store_true",
            default=False,
            help=(
                "With --force-batches, hard-delete swept entities and their "
                "batch-scoped history instead of tombstoning. Permitted if and "
                "only if DEBUG=True. See req-grid-import-grift-sweep-purge."
            ),
        )

    def handle(self, *args, **options):
        from django.conf import settings

        all_plugins = options["all_plugins"]
        plugin_slugs = options["plugin_slugs"]
        bundle_name = options["bundle_name"]
        dry_run = options["dry_run"]
        force_batches_raw = options["force_batches"]
        sweep_strict = options["sweep_strict"]
        purge = options["purge"]

        force_batches: list[str] = [
            b.strip() for b in force_batches_raw.split(",") if b.strip()
        ] if force_batches_raw else []

        # Fail fast with operator-friendly errors before touching any files.
        if (force_batches or purge) and not getattr(settings, "DEBUG", False):
            raise CommandError(
                "--force-batches and --purge are permitted if and only if DEBUG=True. "
                "This invariant is enforced by req-grid-import-grift-force-reimport and "
                "req-grid-import-grift-sweep-purge — refusing the invocation."
            )
        if purge and not force_batches:
            raise CommandError(
                "--purge requires --force-batches; name the batches to purge explicitly."
            )
        if sweep_strict and not force_batches:
            raise CommandError(
                "--sweep-strict requires --force-batches; it only affects sweeps on force re-import."
            )

        plugin_configs = self._resolve_plugins(all_plugins, plugin_slugs)

        if not plugin_configs:
            raise CommandError("No matching TAP plugins found.")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run mode: no database writes."))
        if force_batches:
            self.stdout.write(
                self.style.WARNING(
                    f"Force re-import mode: {len(force_batches)} batch(es) named. "
                    + ("Purge enabled. " if purge else "")
                    + ("Strict sweep enabled. " if sweep_strict else "")
                )
            )

        total_imported = 0
        total_errors = 0

        for config in plugin_configs:
            imported, errors = self._import_plugin(
                config, bundle_name, dry_run,
                force_batches=force_batches,
                sweep_strict=sweep_strict,
                purge=purge,
            )
            total_imported += imported
            total_errors += errors

        if total_errors:
            # Raise CommandError so the process exits non-zero. Callers like
            # scripts/spawn-session.sh rely on this to abort the spawn (and
            # fire its failure trap) instead of silently leaving the session
            # in a partially-seeded state.
            raise CommandError(
                f"Completed with {total_errors} error(s); "
                f"{total_imported} bundle(s) imported successfully."
            )
        self.stdout.write(self.style.SUCCESS(f"Done. {total_imported} bundle(s) imported."))

    # ---------------------------------------------------------------------------

    def _resolve_plugins(
        self,
        all_plugins: bool,
        plugin_slugs: list[str],
    ) -> list[TapPluginConfig]:
        tap_configs = [app_config for app_config in apps.get_app_configs() if isinstance(app_config, TapPluginConfig)]

        if all_plugins:
            return tap_configs

        result = []
        for slug in plugin_slugs:
            match = next(
                (c for c in tap_configs if c.manifest and c.manifest.slug == slug),
                None,
            )
            if match is None:
                raise CommandError(
                    f"No TAP plugin with slug '{slug}' found in INSTALLED_APPS. "
                    f"Available: {[c.manifest.slug for c in tap_configs if c.manifest]}"
                )
            result.append(match)
        return result

    def _import_plugin(
        self,
        config: TapPluginConfig,
        bundle_name: str | None,
        dry_run: bool,
        *,
        force_batches: list[str] | None = None,
        sweep_strict: bool = False,
        purge: bool = False,
    ) -> tuple[int, int]:
        manifest = config.manifest
        if manifest is None:
            self.stderr.write(self.style.ERROR(f"  [{config.name}] No manifest loaded; skipping."))
            return 0, 1

        bundles = manifest.grift
        if bundle_name:
            bundles = [b for b in bundles if b.name == bundle_name]
            if not bundles:
                self.stderr.write(
                    self.style.ERROR(f"  [{manifest.slug}] Bundle '{bundle_name}' not declared in manifest; skipping.")
                )
                return 0, 1

        if not bundles:
            self.stdout.write(f"  [{manifest.slug}] No GRIFT bundles declared; nothing to import.")
            return 0, 0

        imported = 0
        errors = 0

        for bundle in bundles:
            grift_path = manifest.plugin_root / bundle.path
            self.stdout.write(f"  [{manifest.slug}] Importing bundle '{bundle.name}' from {bundle.path} ...")

            try:
                with open(grift_path) as fh:
                    document = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                self.stderr.write(self.style.ERROR(f"    Failed to read '{bundle.path}': {exc}"))
                errors += 1
                continue

            if dry_run:
                self._dry_run_bundle(manifest.slug, bundle.name, document)
                imported += 1
                continue

            result = self._run_import(
                document,
                force_batches=force_batches or [],
                sweep_strict=sweep_strict,
                purge=purge,
            )
            self._report_result(manifest.slug, bundle.name, result)

            if result.success:
                imported += 1
            else:
                errors += 1

        return imported, errors

    def _run_import(
        self,
        document: dict,
        *,
        force_batches: list[str] | None = None,
        sweep_strict: bool = False,
        purge: bool = False,
    ) -> object:
        from tap_grid.grift import grift_import

        return grift_import(
            document,
            dangling_edge_mode="warn",
            actor=None,
            force_batches=force_batches or None,
            sweep_strict=sweep_strict,
            purge=purge,
        )

    def _dry_run_bundle(self, plugin_slug: str, bundle_name: str, document: dict) -> None:
        """Validate a GRIFT document without writing to the database."""
        import jsonschema

        from tap_grid.grift import GRIFT_DOCUMENT_SCHEMA

        try:
            jsonschema.validate(document, GRIFT_DOCUMENT_SCHEMA)
        except jsonschema.ValidationError as exc:
            self.stderr.write(self.style.ERROR(f"    [{plugin_slug}/{bundle_name}] Schema error: {exc.message}"))
            return

        batch_count = len(document.get("batches", []))
        node_count = sum(len(b.get("nodes", [])) for b in document.get("batches", []))
        edge_count = sum(len(b.get("edges", [])) for b in document.get("batches", []))
        self.stdout.write(
            self.style.SUCCESS(
                f"    [{plugin_slug}/{bundle_name}] Valid — "
                f"{batch_count} batch(es), {node_count} node(s), {edge_count} edge(s)."
            )
        )

    def _report_result(self, plugin_slug: str, bundle_name: str, result) -> None:
        counts = result.counts
        label = f"[{plugin_slug}/{bundle_name}]"

        if result.success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {label} OK — "
                    f"{counts.batches_imported} batch(es), "
                    f"{counts.nodes_imported} node(s), "
                    f"{counts.edges_imported} edge(s) imported"
                    + (f", {counts.batches_force_reimported} force-reimported" if counts.batches_force_reimported else "")
                    + (f", {counts.entities_swept} swept" if counts.entities_swept else "")
                    + (f" ({counts.entities_purged} purged)" if counts.entities_purged else "")
                    + (f", {counts.sweep_skipped} sweep skip(s)" if counts.sweep_skipped else "")
                    + (f", {counts.edges_skipped} edge(s) skipped" if counts.edges_skipped else "")
                    + (f", {counts.warnings} warning(s)" if counts.warnings else "")
                    + "."
                )
            )
        else:
            self.stderr.write(self.style.ERROR(f"    {label} FAILED:"))
            for issue in result.errors:
                self.stderr.write(f"      [{issue.phase}] {issue.code} at {issue.path}: {issue.message}")
