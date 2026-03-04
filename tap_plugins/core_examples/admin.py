"""Admin configuration for core_examples plugin."""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from tap_plugins.core_examples.models import Concept, Precept


@admin.register(Concept)
class ConceptAdmin(SimpleHistoryAdmin):
    """Admin for Concept with history timeline."""

    list_display = ["entity"]
    search_fields = ["entity__display_name", "summary"]
    readonly_fields = ["entity", "batch_id"]
    history_list_display = ["history_user", "history_date", "history_type"]


@admin.register(Precept)
class PreceptAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for Precept (no history tracking)."""

    list_display = ["entity"]
    search_fields = ["entity__display_name", "statement"]
    readonly_fields = ["entity", "batch_id"]
