"""Strip the dead v0 `search-id` binding key from USES_SEARCH edge properties.

The key was the v0 layout-definition role-name binding — written by the
entity-viewer/editor GRIFT seeds, read by no code, superseded by the v1
hotlink-validated binding model (see `req-grid-edge-schema-required` in
tap_grid/specs/spec-grid-edge.md, decision 2026-08-10). The seeds no longer
write it; this cleans rows seeded before that change so USES_SEARCH edges
carry empty properties, as the (schema-less) type now requires.

Direct ORM access is the sanctioned path in migrations.
"""

from typing import Any

from django.db import migrations


def strip_search_id(apps: Any, schema_editor: Any) -> None:
    Edge = apps.get_model("tap_grid", "Edge")
    for edge in Edge.objects.filter(edge_type="USES_SEARCH").exclude(properties={}):
        if "search-id" in edge.properties:
            del edge.properties["search-id"]
            edge.save(update_fields=["properties"])


class Migration(migrations.Migration):
    dependencies = [
        ("tap_web", "0001_initial"),
        ("tap_grid", "0001_initial"),
    ]

    operations = [
        # Irreversible-by-design: the key is dead; nothing can want it back.
        migrations.RunPython(strip_search_id, migrations.RunPython.noop),
    ]
