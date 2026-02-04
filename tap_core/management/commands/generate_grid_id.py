"""
Management command to generate a TAP Grid ID.

Usage:
    docker compose exec web uv run python manage.py generate_grid_id

Generates a UUIDv7 value to use as this installation's TAP_GRID_ID.
The generated value should be added to your docker-compose.yml environment
section (or .env file) so it persists across container restarts.

The Grid ID is immutable for the lifetime of the installation. It is stamped
on every Entity as originating_grid_id and will be used for federation
between TAP instances.
"""

import uuid

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate a UUIDv7 Grid ID for this TAP installation"

    def handle(self, *args: object, **options: object) -> None:
        grid_id = str(uuid.uuid7())

        self.stdout.write("")
        self.stdout.write("Generated TAP Grid ID:")
        self.stdout.write(self.style.SUCCESS(f"  {grid_id}"))
        self.stdout.write("")
        self.stdout.write("Add this to your docker-compose.yml under web > environment:")
        self.stdout.write(f'  TAP_GRID_ID: "{grid_id}"')
        self.stdout.write("")
        self.stdout.write("This ID is permanent. Once set, do not change it.")
        self.stdout.write("")
