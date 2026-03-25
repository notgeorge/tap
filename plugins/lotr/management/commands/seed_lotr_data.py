"""
Seed LOTR development data for the landing page graph visualization.

Usage:
    docker compose exec web uv run python manage.py seed_lotr_data

Creates Middle-earth entities and edges for development and testing.
Only runs when DEBUG=True. Idempotent - safe to run multiple times.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from tap_grid.models import Edge, Entity, Search
from plugins.lotr.models import Artifact, Character, Faction, Location, Race


class Command(BaseCommand):
    help = "Seed LOTR data (characters, locations, artifacts, edges). Requires DEBUG=True."

    # Characters
    CHARACTERS = [
        {"name": "Frodo Baggins", "title": "Ring-bearer", "bio": "A hobbit of the Shire who inherits the One Ring."},
        {"name": "Gandalf", "title": "The Grey", "bio": "A wizard and member of the Istari."},
        {"name": "Aragorn", "title": "King of Gondor", "bio": "Heir of Isildur, ranger of the North."},
        {"name": "Samwise Gamgee", "title": "Gardener", "bio": "Frodo's loyal companion."},
        {"name": "Legolas", "title": "Prince of Mirkwood", "bio": "An elven archer."},
        {"name": "Gimli", "title": "Son of Gloin", "bio": "A dwarf warrior."},
        {"name": "Sauron", "title": "The Dark Lord", "bio": "Creator of the One Ring."},
        {"name": "Bilbo Baggins", "title": "Burglar", "bio": "Frodo's uncle, found the Ring."},
    ]

    # Locations
    LOCATIONS = [
        {"name": "The Shire", "realm": "Eriador", "description": "Peaceful homeland of the Hobbits."},
        {"name": "Rivendell", "realm": "Eriador", "description": "Elven refuge of Elrond."},
        {"name": "Mordor", "realm": "Dark Lands", "description": "Domain of Sauron."},
        {"name": "Gondor", "realm": "South Kingdom", "description": "Kingdom of Men."},
        {"name": "Minas Tirith", "realm": "Gondor", "description": "The White City."},
        {"name": "Mount Doom", "realm": "Mordor", "description": "Where the Ring was forged."},
        {"name": "Mirkwood", "realm": "Rhovanion", "description": "Great forest of the Wood-elves."},
    ]

    # Artifacts
    ARTIFACTS = [
        {"name": "The One Ring", "power": "Dominion over all rings of power.", "origin": "Mount Doom"},
        {"name": "Sting", "power": "Glows blue near orcs.", "origin": "Gondolin"},
        {"name": "Anduril", "power": "Reforged from Narsil.", "origin": "Rivendell"},
        {"name": "Glamdring", "power": "Foe-hammer of Gondolin.", "origin": "Gondolin"},
    ]

    # Races
    RACES = [
        {"name": "Hobbits", "homeland": "The Shire", "traits": "Small, fond of comfort and food."},
        {"name": "Elves", "homeland": "Various", "traits": "Immortal, wise, skilled in crafts."},
        {"name": "Dwarves", "homeland": "Erebor", "traits": "Miners, smiths, fierce warriors."},
        {"name": "Men", "homeland": "Various", "traits": "Mortal, ambitious, numerous."},
        {"name": "Wizards", "homeland": "Valinor", "traits": "Maiar spirits in mortal form."},
    ]

    # Factions
    FACTIONS = [
        {"name": "Fellowship of the Ring", "purpose": "Destroy the One Ring."},
        {"name": "Forces of Mordor", "purpose": "Conquer Middle-earth."},
        {"name": "Rohan", "purpose": "Defend the Riddermark."},
    ]

    # Edges to create (source_name, target_name, edge_type)
    EDGES = [
        # WIELDS edges
        ("Frodo Baggins", "The One Ring", "WIELDS"),
        ("Frodo Baggins", "Sting", "WIELDS"),
        ("Aragorn", "Anduril", "WIELDS"),
        ("Gandalf", "Glamdring", "WIELDS"),
        # BELONGS_TO edges
        ("Frodo Baggins", "Hobbits", "BELONGS_TO"),
        ("Samwise Gamgee", "Hobbits", "BELONGS_TO"),
        ("Bilbo Baggins", "Hobbits", "BELONGS_TO"),
        ("Gandalf", "Wizards", "BELONGS_TO"),
        ("Aragorn", "Men", "BELONGS_TO"),
        ("Legolas", "Elves", "BELONGS_TO"),
        ("Gimli", "Dwarves", "BELONGS_TO"),
        # LOCATED_IN edges
        ("Frodo Baggins", "The Shire", "LOCATED_IN"),
        ("Bilbo Baggins", "The Shire", "LOCATED_IN"),
        ("Sauron", "Mordor", "LOCATED_IN"),
        ("Legolas", "Mirkwood", "LOCATED_IN"),
        # MEMBER_OF edges
        ("Frodo Baggins", "Fellowship of the Ring", "MEMBER_OF"),
        ("Gandalf", "Fellowship of the Ring", "MEMBER_OF"),
        ("Aragorn", "Fellowship of the Ring", "MEMBER_OF"),
        ("Samwise Gamgee", "Fellowship of the Ring", "MEMBER_OF"),
        ("Legolas", "Fellowship of the Ring", "MEMBER_OF"),
        ("Gimli", "Fellowship of the Ring", "MEMBER_OF"),
        ("Sauron", "Forces of Mordor", "MEMBER_OF"),
        # ALLIES_WITH edges (character-character)
        ("Frodo Baggins", "Samwise Gamgee", "ALLIES_WITH"),
        ("Aragorn", "Gandalf", "ALLIES_WITH"),
        ("Legolas", "Gimli", "ALLIES_WITH"),
        # ENEMIES_WITH edges
        ("Gandalf", "Sauron", "ENEMIES_WITH"),
        ("Aragorn", "Sauron", "ENEMIES_WITH"),
        # FORGED_IN edges
        ("The One Ring", "Mount Doom", "FORGED_IN"),
        # CONTAINS edges
        ("Mordor", "Mount Doom", "CONTAINS"),
        ("Gondor", "Minas Tirith", "CONTAINS"),
        # RULES edges
        ("Aragorn", "Gondor", "RULES"),
        ("Sauron", "Mordor", "RULES"),
        # Faction edges
        ("Fellowship of the Ring", "Forces of Mordor", "ENEMIES_WITH"),
        ("Fellowship of the Ring", "Rohan", "ALLIES_WITH"),
        # MENTORS edge (uses edge constraint, not node constraint)
        ("Gandalf", "Frodo Baggins", "MENTORS"),
        ("Bilbo Baggins", "Frodo Baggins", "MENTORS"),
    ]

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            self.stderr.write(self.style.WARNING("LOTR seed data skipped: DEBUG=False"))
            return

        self.stdout.write("Seeding LOTR data...")
        entities: dict[str, Entity] = {}

        # Create characters
        for char in self.CHARACTERS:
            entity, created = Entity.objects.get_or_create(
                entity_type="character",
                name=char["name"],
            )
            if created:
                Character.objects.create(entity=entity, title=char["title"], bio=char["bio"])
                self.stdout.write(f"  + Character: {char['name']}")
            entities[char["name"]] = entity

        # Create locations
        for loc in self.LOCATIONS:
            entity, created = Entity.objects.get_or_create(
                entity_type="location",
                name=loc["name"],
            )
            if created:
                Location.objects.create(entity=entity, realm=loc["realm"], description=loc["description"])
                self.stdout.write(f"  + Location: {loc['name']}")
            entities[loc["name"]] = entity

        # Create artifacts
        for art in self.ARTIFACTS:
            entity, created = Entity.objects.get_or_create(
                entity_type="artifact",
                name=art["name"],
            )
            if created:
                Artifact.objects.create(entity=entity, power=art["power"], origin=art["origin"])
                self.stdout.write(f"  + Artifact: {art['name']}")
            entities[art["name"]] = entity

        # Create races
        for race in self.RACES:
            entity, created = Entity.objects.get_or_create(
                entity_type="race",
                name=race["name"],
            )
            if created:
                Race.objects.create(entity=entity, homeland=race["homeland"], traits=race["traits"])
                self.stdout.write(f"  + Race: {race['name']}")
            entities[race["name"]] = entity

        # Create factions
        for faction in self.FACTIONS:
            entity, created = Entity.objects.get_or_create(
                entity_type="faction",
                name=faction["name"],
            )
            if created:
                Faction.objects.create(entity=entity, purpose=faction["purpose"])
                self.stdout.write(f"  + Faction: {faction['name']}")
            entities[faction["name"]] = entity

        # Create edges
        edge_count = 0
        for source_name, target_name, edge_type in self.EDGES:
            from_entity = entities.get(source_name)
            to_entity = entities.get(target_name)

            if not from_entity or not to_entity:
                self.stderr.write(f"  ! Missing entity for edge: {source_name} -> {target_name}")
                continue

            edge_exists = Edge.objects.filter(
                from_entity=from_entity,
                to_entity=to_entity,
                edge_type=edge_type,
            ).exists()

            if not edge_exists:
                edge_entity = Entity.objects.create(
                    entity_type="edge",
                    name=edge_type,
                )
                Edge.objects.create(
                    entity=edge_entity,
                    from_entity=from_entity,
                    to_entity=to_entity,
                    edge_type=edge_type,
                )
                self.stdout.write(f"  + Edge: {source_name} --{edge_type}--> {target_name}")
                edge_count += 1

        self.stdout.write(self.style.SUCCESS(f"LOTR seed complete: {len(entities)} entities, {edge_count} new edges."))

        # Create Search objects
        search_count = self._seed_searches()
        self.stdout.write(self.style.SUCCESS(f"  + {search_count} new searches seeded."))

        # Clean up any standalone FLIP demo page from earlier iterations.
        self._cleanup_flip_demo_page()

        # Create web pages
        self._seed_web_page()
        self._seed_characters_page()
        self._seed_default_landing()

    def _seed_web_page(self) -> None:
        """Create a Middle-earth welcome Page with a single Text Panel. Idempotent."""
        from tap_grid.models import Edge, Entity
        from tap_web.models import Page, Panel
        from tap_web.panels.text_panel import TextPanelType

        # Panel
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

        # Page
        layout = {
            "columns": {
                "col-1": {
                    "width": "1fr",
                    "rows": {
                        "row-1": {"panel-id": "main"},
                    },
                }
            }
        }
        page, page_created = Page.objects.get_or_create(
            slug="/middle-earth",
            defaults={
                "name": "Middle-earth",
                "layout": layout,
            },
        )
        if page_created:
            self.stdout.write("  + Page: /middle-earth")

        # USES_PANEL edge linking page → panel with panel-id "main"
        edge_exists = Edge.objects.filter(
            from_entity=page.entity,
            to_entity=panel.entity,
            edge_type="USES_PANEL",
        ).exists()
        if not edge_exists:
            edge_entity = Entity.objects.create(
                entity_type="edge",
                name="USES_PANEL",
            )
            Edge.objects.create(
                entity=edge_entity,
                from_entity=page.entity,
                to_entity=panel.entity,
                edge_type="USES_PANEL",
                properties={"hotlink": {"model": "page", "spec": "page-panels", "value": "main"}},
            )
            self.stdout.write("  + Edge: /middle-earth --USES_PANEL[main]--> welcome panel")

    def _seed_characters_page(self) -> None:
        """Create a /middle-earth/characters Page with a Table Panel of characters. Idempotent.

        Creates:
          - A Table Panel linked to the 'All LOTR Characters' search via USES_SEARCH.
          - A Page at /middle-earth/characters with the panel in its layout.
          - A LandingPage → Page link so the root URL shows the characters table.
        """
        from tap_grid.models import Edge, Entity, Search
        from tap_web.models import Page, Panel
        from tap_web.panels.table_panel import TablePanelType

        # Table Panel
        panel, panel_created = Panel.objects.update_or_create(
            slug="lotr-characters-table",
            defaults={
                "name": "LOTR Characters",
                "view": TablePanelType.view,
                "editor_view": TablePanelType.editor_view,
                "css": TablePanelType.css,
                "js": TablePanelType.js,
                "config": {
                    "column_mode": "common_metadata",
                    "default_limit": 25,
                },
            },
        )
        if panel_created:
            self.stdout.write("  + Panel: LOTR Characters (table)")

        # Link panel → search via USES_SEARCH edge (idempotent)
        try:
            search = Search.objects.get(name="All LOTR Characters")
            uses_search_exists = Edge.objects.filter(
                from_entity=panel.entity,
                to_entity=search.entity,
                edge_type="USES_SEARCH",
            ).exists()
            if not uses_search_exists:
                edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
                Edge.objects.create(
                    entity=edge_entity,
                    from_entity=panel.entity,
                    to_entity=search.entity,
                    edge_type="USES_SEARCH",
                )
                self.stdout.write("  + Edge: lotr-characters-table --USES_SEARCH--> All LOTR Characters")
        except Search.DoesNotExist:
            self.stderr.write("  ! Search 'All LOTR Characters' not found; USES_SEARCH edge skipped.")

        # Page
        layout = {
            "columns": {
                "col-1": {
                    "width": "1fr",
                    "rows": {
                        "row-1": {"panel-id": "characters"},
                    },
                }
            }
        }
        page, page_created = Page.objects.get_or_create(
            slug="/middle-earth/characters",
            defaults={
                "name": "Middle-earth Characters",
                "layout": layout,
            },
        )
        if page_created:
            self.stdout.write("  + Page: /middle-earth/characters")

        # USES_PANEL edge: page → panel with panel-id "characters"
        uses_panel_exists = Edge.objects.filter(
            from_entity=page.entity,
            to_entity=panel.entity,
            edge_type="USES_PANEL",
        ).exists()
        if not uses_panel_exists:
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
        """Seed the default landing page: viz panel (top) + nodes table. Idempotent.

        Graph: LandingPage --USES_LANDING_PAGE--> Page
               Page --USES_PANEL[graph]--> viz Panel
               Page --USES_PANEL[nodes]--> table Panel
               viz Panel --USES_LAYOUT[layout-id=default]--> Layout
               Layout --USES_SEARCH[search-id=main]--> Search (all entities)
               table Panel --USES_SEARCH--> Search (all entities)
        """
        from tap_grid.models import Edge, Entity, Search
        from tap_web.models import LandingPage, Page, Panel
        from tap_web.panels.table_panel import TablePanelType
        from tap_viz.models import Layout
        from tap_viz.panels.graph_panel import GraphPanelType

        # --- Searches ---
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

        # --- Layout entity ---
        layout_entity, layout_entity_created = Entity.objects.get_or_create(
            entity_type="layout",
            name="Grid Overview",
        )
        _layout_definition = {
            "inputs": [],
            "steps": [{"type": "search", "search-id": "main"}],
            "presentation": {"placement": "cytoscape:grid"},
            "interactions": {},
        }
        layout, layout_created = Layout.objects.update_or_create(
            entity=layout_entity,
            defaults={
                "name": "Grid Overview",
                "description": "All entities in the grid shown as a graph.",
                "definition": _layout_definition,
            },
        )
        if layout_created:
            self.stdout.write("  + Layout: Grid Overview")

        # USES_SEARCH: Layout -> all_entities_search
        if not Edge.objects.filter(
            from_entity=layout.entity,
            to_entity=all_entities_search.entity,
            edge_type="USES_SEARCH",
        ).exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=layout.entity,
                to_entity=all_entities_search.entity,
                edge_type="USES_SEARCH",
                properties={"search-id": "main"},
            )
            self.stdout.write("  + Edge: Grid Overview --USES_SEARCH[main]--> All Grid Entities")

        # USES_SEARCH: Layout -> all_edges_search
        if not Edge.objects.filter(
            from_entity=layout.entity,
            to_entity=all_edges_search.entity,
            edge_type="USES_SEARCH",
        ).exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=layout.entity,
                to_entity=all_edges_search.entity,
                edge_type="USES_SEARCH",
                properties={"search-id": "edges"},
            )
            self.stdout.write("  + Edge: Grid Overview --USES_SEARCH[edges]--> All Grid Edges")

        # --- Graph panel ---
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

        # USES_LAYOUT: graph_panel -> layout
        if not Edge.objects.filter(
            from_entity=graph_panel.entity,
            to_entity=layout.entity,
            edge_type="USES_LAYOUT",
        ).exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_LAYOUT")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=graph_panel.entity,
                to_entity=layout.entity,
                edge_type="USES_LAYOUT",
                properties={"layout-id": "default"},
            )
            self.stdout.write("  + Edge: grid-overview-graph --USES_LAYOUT[default]--> Grid Overview")

        # --- Nodes table panel ---
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

        # USES_SEARCH: table_panel -> all_entities_search
        if not Edge.objects.filter(
            from_entity=table_panel.entity,
            to_entity=all_entities_search.entity,
            edge_type="USES_SEARCH",
        ).exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=table_panel.entity,
                to_entity=all_entities_search.entity,
                edge_type="USES_SEARCH",
            )
            self.stdout.write("  + Edge: grid-all-nodes-table --USES_SEARCH--> All Grid Entities")

        # --- Page ---
        page_layout = {
            "columns": {
                "col-1": {
                    "width": "1fr",
                    "rows": {
                        "row-1": {"panel-id": "graph"},
                        "row-2": {"panel-id": "nodes"},
                    },
                }
            }
        }
        page, page_created = Page.objects.get_or_create(
            slug="/grid",
            defaults={"name": "Grid", "layout": page_layout},
        )
        if page_created:
            self.stdout.write("  + Page: /grid (Grid landing)")

        # USES_PANEL: page -> graph_panel
        if not Edge.objects.filter(
            from_entity=page.entity, to_entity=graph_panel.entity, edge_type="USES_PANEL"
        ).exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_PANEL")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=page.entity,
                to_entity=graph_panel.entity,
                edge_type="USES_PANEL",
                properties={"hotlink": {"model": "page", "spec": "page-panels", "value": "graph"}},
            )
            self.stdout.write("  + Edge: /grid --USES_PANEL[graph]--> grid-overview-graph")

        # USES_PANEL: page -> table_panel
        if not Edge.objects.filter(
            from_entity=page.entity, to_entity=table_panel.entity, edge_type="USES_PANEL"
        ).exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_PANEL")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=page.entity,
                to_entity=table_panel.entity,
                edge_type="USES_PANEL",
                properties={"hotlink": {"model": "page", "spec": "page-panels", "value": "nodes"}},
            )
            self.stdout.write("  + Edge: /grid --USES_PANEL[nodes]--> grid-all-nodes-table")

        # --- LandingPage ---
        landing, landing_created = LandingPage.objects.get_or_create(
            name="Default",
            defaults={"description": "Default TAP landing page."},
        )
        if landing_created:
            self.stdout.write("  + LandingPage: Default")

        # USES_LANDING_PAGE: landing -> page
        if not Edge.objects.filter(
            from_entity=landing.entity, to_entity=page.entity, edge_type="USES_LANDING_PAGE"
        ).exists():
            edge_entity = Entity.objects.create(entity_type="edge", name="USES_LANDING_PAGE")
            Edge.objects.create(
                entity=edge_entity,
                from_entity=landing.entity,
                to_entity=page.entity,
                edge_type="USES_LANDING_PAGE",
            )
            self.stdout.write("  + Edge: LandingPage --USES_LANDING_PAGE--> /grid")

    def _seed_searches(self) -> int:
        """Create reusable Search objects for LOTR data exploration. Idempotent."""
        searches = [
            # --- ORM searches (declarative, no runner needed) ---
            {
                "name": "All LOTR Characters",
                "description": "Every character in Middle-earth.",
                "search_type": "orm",
                "root": "node",
                "definition": {
                    "filters": {"entity_type": "character"},
                    "order_by": ["name"],
                },
            },
            {
                "name": "All LOTR Locations",
                "description": "Every location in Middle-earth.",
                "search_type": "orm",
                "root": "node",
                "definition": {
                    "filters": {"entity_type": "location"},
                    "order_by": ["name"],
                },
            },
            {
                "name": "All LOTR Artifacts",
                "description": "Every significant artifact.",
                "search_type": "orm",
                "root": "node",
                "definition": {
                    "filters": {"entity_type": "artifact"},
                    "order_by": ["name"],
                },
            },
            {
                "name": "Characters and Their Artifacts",
                "description": "Characters with the artifacts they wield (one-hop graph).",
                "search_type": "orm",
                "root": "node",
                "definition": {
                    "filters": {"entity_type": "character"},
                    "hops": [
                        {
                            "direction": "out",
                            "edge_type": "WIELDS",
                            "target_filters": {"entity_type": "artifact"},
                        }
                    ],
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
                    "hops": [
                        {
                            "direction": "out",
                            "edge_type": "LOCATED_IN",
                            "target_filters": {"entity_type": "location"},
                        }
                    ],
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
            # --- Module search (runner-backed, includes typed model fields) ---
            {
                "name": "Characters with Bio",
                "description": "All characters with title and bio from the typed model.",
                "search_type": "module",
                "root": "node",
                "definition": {
                    "runner_key": "plugins.lotr.searches:list-characters-with-bio"
                },
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
        return count

    def _cleanup_flip_demo_page(self) -> None:
        """Remove the standalone /flip demo page and panel from earlier iterations.

        Deletes via the Entity spine so that cascade removes the Page/Panel records too.
        """
        from tap_grid.models import Entity

        entity_ids = list(
            Entity.objects.filter(entity_type__in=["page", "panel"], name__in=["FLIP Demo", "Frodo Baggins — Field Provenance"]).values_list("pk", flat=True)
        )
        if entity_ids:
            deleted = Entity.objects.filter(pk__in=entity_ids).delete()
            self.stdout.write(f"  - Cleaned up {deleted[0]} old FLIP demo entities.")
