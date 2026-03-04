"""tap_viz admin configuration."""

from django.contrib import admin

from tap_viz.models import Layout


@admin.register(Layout)
class LayoutAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin interface for Layout model."""

    list_display = ["name", "entity_id"]
    search_fields = ["name", "description"]
    readonly_fields = ["entity"]
