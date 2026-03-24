# Generated 2026-03-24 — migrate USES_PANEL edge properties from panel-id to hotlink object.
#
# Rewrites properties["panel-id"] → properties["hotlink"]["value"] on all existing
# USES_PANEL edges that have not already been migrated. This satisfies
# req-grid-hotlink-edge-data-5 (Page Panel Migration Required).

from django.db import migrations


def migrate_uses_panel_hotlinks(apps, schema_editor):
    """Convert USES_PANEL edge properties from panel-id to hotlink format."""
    Edge = apps.get_model("tap_grid", "Edge")

    edges = Edge.objects.filter(edge_type="USES_PANEL")
    to_update = []

    for edge in edges:
        props = edge.properties or {}
        # Skip edges already in the hotlink format.
        if "hotlink" in props:
            continue
        panel_id = props.get("panel-id")
        if panel_id is None:
            continue
        new_props = {k: v for k, v in props.items() if k != "panel-id"}
        new_props["hotlink"] = {
            "model": "page",
            "spec": "page-panels",
            "value": panel_id,
        }
        edge.properties = new_props
        to_update.append(edge)

    if to_update:
        Edge.objects.bulk_update(to_update, ["properties"])


def reverse_uses_panel_hotlinks(apps, schema_editor):
    """Restore USES_PANEL edge properties from hotlink format back to panel-id."""
    Edge = apps.get_model("tap_grid", "Edge")

    edges = Edge.objects.filter(edge_type="USES_PANEL")
    to_update = []

    for edge in edges:
        props = edge.properties or {}
        hotlink = props.get("hotlink", {})
        if not hotlink or "panel-id" in props:
            continue
        value = hotlink.get("value")
        if value is None:
            continue
        new_props = {k: v for k, v in props.items() if k != "hotlink"}
        new_props["panel-id"] = value
        edge.properties = new_props
        to_update.append(edge)

    if to_update:
        Edge.objects.bulk_update(to_update, ["properties"])


class Migration(migrations.Migration):

    dependencies = [
        ("tap_web", "0004_rename_title_landingpage_name_rename_title_page_name_and_more"),
        ("tap_grid", "0010_drop_core_examples_tables"),
    ]

    operations = [
        migrations.RunPython(
            migrate_uses_panel_hotlinks,
            reverse_code=reverse_uses_panel_hotlinks,
        ),
    ]
