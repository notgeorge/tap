"""
Seed development data for the core_examples plugin.

Usage:
    docker compose exec web uv run python manage.py seed_dev_data

Creates example entities (concept, precept, edge) for development and testing.
Only runs when DEBUG=True. Idempotent — safe to run multiple times.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from tap_grid.models import Edge, Entity
from tap_plugins.core_examples.models import Concept, Precept


class Command(BaseCommand):
    help = "Seed development data (concept, precept, edge). Requires DEBUG=True."

    # Seed data definitions
    CONCEPT_NAME = "It's the connections between things that are important"
    CONCEPT_SUMMARY = (
        "The fundamental insight that relationships and connections " "often matter more than isolated objects."
    )

    PRECEPT_NAME = "Name your things"
    PRECEPT_STATEMENT = "Give meaningful names to entities so they can be referenced and reasoned about."

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            self.stderr.write(self.style.WARNING("Seed data skipped: DEBUG=False (production mode)"))
            return

        created_count = 0

        # Create or get concept
        concept_entity, concept_created = Entity.objects.get_or_create(
            entity_type="concept",
            display_name=self.CONCEPT_NAME,
        )
        if concept_created:
            Concept.objects.create(entity=concept_entity, summary=self.CONCEPT_SUMMARY)
            self.stdout.write(f"  Created concept: {self.CONCEPT_NAME}")
            created_count += 1
        else:
            self.stdout.write(f"  Exists: {self.CONCEPT_NAME}")

        # Create or get precept
        precept_entity, precept_created = Entity.objects.get_or_create(
            entity_type="precept",
            display_name=self.PRECEPT_NAME,
        )
        if precept_created:
            Precept.objects.create(entity=precept_entity, statement=self.PRECEPT_STATEMENT)
            self.stdout.write(f"  Created precept: {self.PRECEPT_NAME}")
            created_count += 1
        else:
            self.stdout.write(f"  Exists: {self.PRECEPT_NAME}")

        # Create edge only if both entities are new (or edge doesn't exist)
        edge_exists = Edge.objects.filter(
            from_entity=concept_entity,
            to_entity=precept_entity,
            edge_type="APPLIES_TO",
        ).exists()

        if not edge_exists:
            edge_entity = Entity.objects.create(
                entity_type="edge",
                display_name="APPLIES_TO",
            )
            Edge.objects.create(
                entity=edge_entity,
                from_entity=concept_entity,
                to_entity=precept_entity,
                edge_type="APPLIES_TO",
            )
            self.stdout.write("  Created edge: APPLIES_TO")
            created_count += 1
        else:
            self.stdout.write("  Exists: APPLIES_TO edge")

        if created_count > 0:
            self.stdout.write(self.style.SUCCESS(f"Seeded {created_count} entities."))
        else:
            self.stdout.write(self.style.SUCCESS("All seed data already exists."))
