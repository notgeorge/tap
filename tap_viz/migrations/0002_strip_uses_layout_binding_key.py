"""Strip the dead v0 `layout-id` binding key from USES_LAYOUT edge properties.

Twin of tap_web's 0002 for the USES_SEARCH key — see that migration's
docstring and `req-grid-edge-schema-required` (tap_grid/specs/spec-grid-edge.md,
decision 2026-08-10). Only the legacy `layout-id` key is stripped; USES_LAYOUT
edges carrying `hotlink` properties are the live system-owned lane and are
left untouched.

Direct ORM access is the sanctioned path in migrations.
"""

from typing import Any

from django.db import migrations


def strip_layout_id(apps: Any, schema_editor: Any) -> None:
    Edge = apps.get_model("tap_grid", "Edge")
    for edge in Edge.objects.filter(edge_type="USES_LAYOUT").exclude(properties={}):
        if "layout-id" in edge.properties:
            del edge.properties["layout-id"]
            edge.save(update_fields=["properties"])


class Migration(migrations.Migration):
    dependencies = [
        ("tap_viz", "0001_initial"),
        ("tap_grid", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(strip_layout_id, migrations.RunPython.noop),
    ]
