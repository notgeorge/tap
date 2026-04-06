"""
Seed LOTR development data: imports bundled GRIFT data then scaffolds web UI.

Usage:
    docker compose exec web uv run python manage.py seed_lotr_data

Steps:
    1. Import core-data.grift.json via grift_import (characters, locations,
       artifacts, races, factions, edges).
    2. Seed Search objects for LOTR data exploration.
    3. Scaffold web pages and panels (Middle-earth, /grid landing page).

Only runs when DEBUG=True. Idempotent — safe to run multiple times.
"""

import json

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand

from tap_plugins.base import TapPluginConfig


class Command(BaseCommand):
    help = "Seed LOTR data via GRIFT import + web scaffold. Requires DEBUG=True."

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            self.stderr.write(self.style.WARNING("LOTR seed data skipped: DEBUG=False"))
            return

        self._import_grift()
        self._seed_searches()
        self._cleanup_flip_demo_page()
        self._seed_web_page()
        self._seed_characters_page()
        self._seed_default_landing()

    # ---------------------------------------------------------------------------
    # GRIFT import
    # ---------------------------------------------------------------------------

    def _import_grift(self) -> None:
        """Import core-data.grift.json for the lotr plugin."""
        from tap_grid.grift import grift_import

        lotr_config = apps.get_app_config("lotr")
        if not isinstance(lotr_config, TapPluginConfig) or lotr_config.manifest is None:
            self.stderr.write(self.style.ERROR("  ! lotr plugin manifest not loaded; skipping GRIFT import."))
            return

        manifest = lotr_config.manifest
        bundles = manifest.grift

        if not bundles:
            self.stderr.write(self.style.WARNING("  ! No GRIFT bundles declared in lotr manifest."))
            return

        for bundle in bundles:
            grift_path = manifest.plugin_root / bundle.path
            self.stdout.write(f"  Importing GRIFT bundle '{bundle.name}' ...")

            with open(grift_path) as fh:
                document = json.load(fh)

            result = grift_import(document, dangling_edge_mode="warn", actor=None)
            counts = result.counts

            if result.success:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  + {bundle.name}: {counts.nodes_imported} node(s), "
                        f"{counts.edges_imported} edge(s) imported"
                        + (f", {counts.edges_skipped} skipped" if counts.edges_skipped else "")
                        + "."
                    )
                )
                for issue in result.issues:
                    self.stdout.write(f"    ~ {issue.phase}: {issue.message}")
            else:
                self.stderr.write(self.style.ERROR(f"  ! GRIFT import failed for '{bundle.name}':"))
                for issue in result.issues:
                    self.stderr.write(f"    [{issue.phase}] {issue.path}: {issue.message}")

    # ---------------------------------------------------------------------------
    # Search seeding
    # ---------------------------------------------------------------------------

    def _seed_searches(self) -> None:
        """Create reusable Search objects for LOTR data exploration. Idempotent."""
        from tap_grid.models import Search

        searches = [
            {
                "name": "All LOTR Characters",
                "description": "Every character in Middle-earth.",
                "search_type": "orm",
                "root": "node",
                "definition": {"filters": {"entity_type": "character"}, "order_by": ["name"]},
            },
            {
                "name": "All LOTR Locations",
                "description": "Every location in Middle-earth.",
                "search_type": "orm",
                "root": "node",
                "definition": {"filters": {"entity_type": "location"}, "order_by": ["name"]},
            },
            {
                "name": "All LOTR Artifacts",
                "description": "Every significant artifact.",
                "search_type": "orm",
                "root": "node",
                "definition": {"filters": {"entity_type": "artifact"}, "order_by": ["name"]},
            },
            {
                "name": "Characters and Their Artifacts",
                "description": "Characters with the artifacts they wield (one-hop graph).",
                "search_type": "orm",
                "root": "node",
                "definition": {
                    "filters": {"entity_type": "character"},
                    "hops": [{"direction": "out", "edge_type": "WIELDS", "target_filters": {"entity_type": "artifact"}}],
                    "order_by": ["name"],
                },
            },
            {
                "name": "Characters and Their Locations",
                "description": "Characters with where they are located (one-hop graph).",
                "search_type": "orm",
                "root": "node",
                "definition": {
                    "filters": {"entity_type": "character"},
                    "hops": [{"direction": "out", "edge_type": "LOCATED_IN", "target_filters": {"entity_type": "location"}}],
                    "order_by": ["name"],
                },
            },
            {
                "name": "Character Alliances",
                "description": "Characters and who they are allied with.",
                "search_type": "orm",
                "root": "node",
                "definition": {
                    "filters": {"entity_type": "character"},
                    "hops": [{"direction": "out", "edge_type": "ALLIES_WITH"}],
                    "order_by": ["name"],
                },
            },
            {
                "name": "All Fellowship Edges",
                "description": "All relationship edges in the Middle-earth graph.",
                "search_type": "orm",
                "root": "edge",
                "definition": {"filters": {}, "order_by": ["entity_id"]},
            },
            {
                "name": "Characters with Bio",
                "description": "All characters with bio from the typed model.",
                "search_type": "module",
                "root": "node",
                "definition": {"runner_key": "plugins.lotr.searches:list-characters-with-bio"},
            },
        ]

        count = 0
        for spec in searches:
            name = spec.pop("name")
            _, created = Search.objects.update_or_create(
                name=name,
                search_type=spec["search_type"],
                defaults={"name": name, **spec},
            )
            if created:
                self.stdout.write(f"  + Search: {name}")
                count += 1

        self.stdout.write(self.style.SUCCESS(f"  + {count} new search(es) created."))

    # ---------------------------------------------------------------------------
    # Web scaffolding
    # ---------------------------------------------------------------------------

    def _seed_web_page(self) -> None:
        """Create a Middle-earth welcome Page with a single Text Panel. Idempotent."""
        from tap_grid.models import Edge, Entity
        from tap_web.models import Page, Panel
        from tap_web.panels.text_panel import TextPanelType

        panel, panel_created = Panel.objects.get_or_create(
            slug="middle-earth-welcome",
            defaults={
                "name": "Welcome to Middle-earth",
                "view": TextPanelType.view,
                "editor_view": TextPanelType.editor_view,
                "config": {"text": "hello middle earth"},
            },
        )
        if panel_created:
            self.stdout.write("  + Panel: Welcome to Middle-earth")

        layout = {
            "columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "main"}}}}
        }
        page, page_created = Page.objects.get_or_create(
            slug="/middle-earth",
            defaults={"name": "Middle-earth", "layout": layout},
        )
        if page_created:
            self.stdout.write("  + Page: /middle-earth")

        if not Edge.objects.filter(from_entity=page.entity, to_entity=panel.entity, edge_type="USES_PANEL").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_PANEL")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=page.entity,
                to_entity=panel.entity,
                edge_type="USES_PANEL",
                properties={"hotlink": {"model": "page", "spec": "page-panels", "value": "main"}},
            )
            self.stdout.write("  + Edge: /middle-earth --USES_PANEL[main]--> welcome panel")

    def _seed_characters_page(self) -> None:
        """Create a /middle-earth/characters Page with a Table Panel. Idempotent."""
        from tap_grid.models import Edge, Entity, Search
        from tap_web.models import Page, Panel
        from tap_web.panels.table_panel import TablePanelType

        panel, panel_created = Panel.objects.update_or_create(
            slug="lotr-characters-table",
            defaults={
                "name": "LOTR Characters",
                "view": TablePanelType.view,
                "editor_view": TablePanelType.editor_view,
                "css": TablePanelType.css,
                "js": TablePanelType.js,
                "config": {"column_mode": "common_metadata", "default_limit": 25},
            },
        )
        if panel_created:
            self.stdout.write("  + Panel: LOTR Characters (table)")

        try:
            search = Search.objects.get(name="All LOTR Characters")
            if not Edge.objects.filter(from_entity=panel.entity, to_entity=search.entity, edge_type="USES_SEARCH").exists():
                edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
                Edge.objects.create(entity=edge_entity, from_entity=panel.entity, to_entity=search.entity, edge_type="USES_SEARCH")
                self.stdout.write("  + Edge: lotr-characters-table --USES_SEARCH--> All LOTR Characters")
        except Search.DoesNotExist:
            self.stderr.write("  ! Search 'All LOTR Characters' not found; USES_SEARCH edge skipped.")

        layout = {
            "columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "characters"}}}}
        }
        page, page_created = Page.objects.get_or_create(
            slug="/middle-earth/characters",
            defaults={"name": "Middle-earth Characters", "layout": layout},
        )
        if page_created:
            self.stdout.write("  + Page: /middle-earth/characters")

        if not Edge.objects.filter(from_entity=page.entity, to_entity=panel.entity, edge_type="USES_PANEL").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_PANEL")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=page.entity,
                to_entity=panel.entity,
                edge_type="USES_PANEL",
                properties={"hotlink": {"model": "page", "spec": "page-panels", "value": "characters"}},
            )
            self.stdout.write("  + Edge: /middle-earth/characters --USES_PANEL[characters]--> lotr-characters-table")

    def _seed_default_landing(self) -> None:  # noqa: PLR0912
        """Seed the default landing page: viz panel (top) + nodes table. Idempotent."""
        from tap_grid.models import Edge, Entity, Search
        from tap_viz.models import Layout
        from tap_viz.panels.graph_panel import GraphPanelType
        from tap_web.models import LandingPage, Page, Panel
        from tap_web.panels.table_panel import TablePanelType

        all_entities_search, _ = Search.objects.get_or_create(
            name="All Grid Entities",
            defaults={
                "description": "All entity nodes in the grid.",
                "search_type": "orm",
                "root": "node",
                "definition": {"filters": {}, "order_by": ["name"]},
                "default_limit": 200,
                "max_limit": 500,
            },
        )
        all_edges_search, _ = Search.objects.get_or_create(
            name="All Grid Edges",
            defaults={
                "description": "All edges in the grid.",
                "search_type": "orm",
                "root": "edge",
                "definition": {"filters": {}, "order_by": ["entity_id"]},
                "default_limit": 500,
                "max_limit": 2000,
            },
        )

        layout_entity, _ = Entity.objects.get_or_create(entity_type="layout", name="Grid Overview")
        layout, layout_created = Layout.objects.update_or_create(
            entity=layout_entity,
            defaults={
                "name": "Grid Overview",
                "description": "All entities in the grid shown as a graph.",
                "definition": {
                    "inputs": [],
                    "steps": [{"type": "search", "search-id": "main"}],
                    "presentation": {"placement": "cytoscape:grid"},
                    "interactions": {},
                },
            },
        )
        if layout_created:
            self.stdout.write("  + Layout: Grid Overview")

        if not Edge.objects.filter(from_entity=layout.entity, to_entity=all_entities_search.entity, edge_type="USES_SEARCH").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
            Edge.objects.create(entity=edge_entity, from_entity=layout.entity, to_entity=all_entities_search.entity, edge_type="USES_SEARCH", properties={"search-id": "main"})
            self.stdout.write("  + Edge: Grid Overview --USES_SEARCH[main]--> All Grid Entities")

        if not Edge.objects.filter(from_entity=layout.entity, to_entity=all_edges_search.entity, edge_type="USES_SEARCH").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
            Edge.objects.create(entity=edge_entity, from_entity=layout.entity, to_entity=all_edges_search.entity, edge_type="USES_SEARCH", properties={"search-id": "edges"})
            self.stdout.write("  + Edge: Grid Overview --USES_SEARCH[edges]--> All Grid Edges")

        graph_panel, graph_panel_created = Panel.objects.update_or_create(
            slug="grid-overview-graph",
            defaults={
                "name": "Grid Overview",
                "view": GraphPanelType.view,
                "js": GraphPanelType.js,
                "css": GraphPanelType.css,
                "config": {},
            },
        )
        if graph_panel_created:
            self.stdout.write("  + Panel: Grid Overview (graph)")

        if not Edge.objects.filter(from_entity=graph_panel.entity, to_entity=layout.entity, edge_type="USES_LAYOUT").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_LAYOUT")
            Edge.objects.create(entity=edge_entity, from_entity=graph_panel.entity, to_entity=layout.entity, edge_type="USES_LAYOUT", properties={"layout-id": "default"})
            self.stdout.write("  + Edge: grid-overview-graph --USES_LAYOUT[default]--> Grid Overview")

        table_panel, table_panel_created = Panel.objects.update_or_create(
            slug="grid-all-nodes-table",
            defaults={
                "name": "All Entities",
                "view": TablePanelType.view,
                "editor_view": TablePanelType.editor_view,
                "js": TablePanelType.js,
                "css": TablePanelType.css,
                "config": {"column_mode": "common_metadata", "default_limit": 25},
            },
        )
        if table_panel_created:
            self.stdout.write("  + Panel: All Entities (table)")

        if not Edge.objects.filter(from_entity=table_panel.entity, to_entity=all_entities_search.entity, edge_type="USES_SEARCH").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
            Edge.objects.create(entity=edge_entity, from_entity=table_panel.entity, to_entity=all_entities_search.entity, edge_type="USES_SEARCH")
            self.stdout.write("  + Edge: grid-all-nodes-table --USES_SEARCH--> All Grid Entities")

        page_layout = {
            "columns": {
                "col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "graph"}, "row-2": {"panel-id": "nodes"}}}
            }
        }
        page, page_created = Page.objects.get_or_create(slug="/grid", defaults={"name": "Grid", "layout": page_layout})
        if page_created:
            self.stdout.write("  + Page: /grid (Grid landing)")

        if not Edge.objects.filter(from_entity=page.entity, to_entity=graph_panel.entity, edge_type="USES_PANEL").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_PANEL")
            Edge.objects.create(entity=edge_entity, from_entity=page.entity, to_entity=graph_panel.entity, edge_type="USES_PANEL", properties={"hotlink": {"model": "page", "spec": "page-panels", "value": "graph"}})
            self.stdout.write("  + Edge: /grid --USES_PANEL[graph]--> grid-overview-graph")

        if not Edge.objects.filter(from_entity=page.entity, to_entity=table_panel.entity, edge_type="USES_PANEL").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_PANEL")
            Edge.objects.create(entity=edge_entity, from_entity=page.entity, to_entity=table_panel.entity, edge_type="USES_PANEL", properties={"hotlink": {"model": "page", "spec": "page-panels", "value": "nodes"}})
            self.stdout.write("  + Edge: /grid --USES_PANEL[nodes]--> grid-all-nodes-table")

        landing, landing_created = LandingPage.objects.get_or_create(
            name="Default",
            defaults={"description": "Default TAP landing page."},
        )
        if landing_created:
            self.stdout.write("  + LandingPage: Default")

        if not Edge.objects.filter(from_entity=landing.entity, to_entity=page.entity, edge_type="USES_LANDING_PAGE").exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_LANDING_PAGE")
            Edge.objects.create(entity=edge_entity, from_entity=landing.entity, to_entity=page.entity, edge_type="USES_LANDING_PAGE")
            self.stdout.write("  + Edge: LandingPage --USES_LANDING_PAGE--> /grid")

    def _cleanup_flip_demo_page(self) -> None:
        """Remove the standalone /flip demo page and panel from earlier iterations."""
        from tap_grid.models import Entity

        entity_ids = list(
            Entity.objects.filter(
                entity_type__in=["page", "panel"],
                name__in=["FLIP Demo", "Frodo Baggins — Field Provenance"],
            ).values_list("pk", flat=True)
        )
        if entity_ids:
            deleted = Entity.objects.filter(pk__in=entity_ids).delete()
            self.stdout.write(f"  - Cleaned up {deleted[0]} old FLIP demo entities.")
