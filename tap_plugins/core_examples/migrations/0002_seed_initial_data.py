"""
Seed data migration — now a no-op.

This migration previously created initial example entities. That logic has been
moved to the seed_dev_data management command which runs conditionally based
on DEBUG setting.

The migration is preserved (empty) so Django doesn't try to re-apply it on
databases that already ran the original version.

Usage:
    docker compose exec web uv run python manage.py seed_dev_data
"""

from typing import Any

from django.db import migrations


def seed_data(apps: Any, schema_editor: Any) -> None:
    """No-op. Seed data moved to management command."""
    pass


def remove_data(apps: Any, schema_editor: Any) -> None:
    """No-op. Reverse migration preserved for compatibility."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core_examples", "0001_initial"),
        ("tap_grid", "0002_entity_entitytype_edge"),
    ]

    operations = [
        migrations.RunPython(seed_data, remove_data),
    ]
