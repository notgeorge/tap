"""Seed initial example entities."""

from typing import Any

from django.db import migrations


def seed_data(apps: Any, schema_editor: Any) -> None:
    """Create initial concept, precept, and edge."""
    Entity = apps.get_model("tap_core", "Entity")
    Edge = apps.get_model("tap_core", "Edge")
    Concept = apps.get_model("core_examples", "Concept")
    Precept = apps.get_model("core_examples", "Precept")

    # Create the concept entity
    concept_entity = Entity.objects.create(
        entity_type="concept",
        display_name="It's the connections between things that are important",
    )
    Concept.objects.create(
        entity=concept_entity,
        summary="The fundamental insight that relationships and connections often matter more than isolated objects.",
    )

    # Create the precept entity
    precept_entity = Entity.objects.create(
        entity_type="precept",
        display_name="Name your things",
    )
    Precept.objects.create(
        entity=precept_entity,
        statement="Give meaningful names to entities so they can be referenced and reasoned about.",
    )

    # Create the edge entity (edges are also entities via BaseModel)
    edge_entity = Entity.objects.create(
        entity_type="edge",
        display_name="applies_to",
    )
    Edge.objects.create(
        entity=edge_entity,
        from_entity=concept_entity,
        to_entity=precept_entity,
        edge_type="applies_to",
    )


def remove_data(apps: Any, schema_editor: Any) -> None:
    """Remove seeded data."""
    Entity = apps.get_model("tap_core", "Entity")
    Entity.objects.filter(
        display_name__in=[
            "It's the connections between things that are important",
            "Name your things",
            "applies_to",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core_examples", "0001_initial"),
        ("tap_core", "0002_entity_entitytype_edge"),
    ]

    operations = [
        migrations.RunPython(seed_data, remove_data),
    ]
