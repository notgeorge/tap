"""tap_flip admin configuration."""

from django.contrib import admin
from django.http import HttpRequest
from simple_history.admin import SimpleHistoryAdmin

from tap_flip.models import Batch, BatchEvent


@admin.register(Batch)
class BatchAdmin(SimpleHistoryAdmin):
    """Admin for Batch model with history support."""

    list_display = ["entity", "status", "source", "actor", "started_at", "closed_at"]
    list_filter = ["status", "source"]
    search_fields = ["entity__name", "source", "error_message"]
    readonly_fields = ["entity", "started_at"]
    date_hierarchy = "started_at"
    ordering = ["-started_at"]


@admin.register(BatchEvent)
class BatchEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for BatchEvent model (read-only audit log)."""

    list_display = ["id", "batch", "event_type", "entity_type", "model_name", "timestamp", "actor"]
    list_filter = ["event_type", "entity_type", "model_name"]
    search_fields = ["entity_id", "entity_type", "model_name"]
    readonly_fields = [
        "id",
        "batch",
        "event_type",
        "entity_id",
        "entity_type",
        "model_name",
        "timestamp",
        "actor",
        "metadata",
    ]
    date_hierarchy = "timestamp"
    ordering = ["-timestamp"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """BatchEvents are append-only via signals."""
        return False

    def has_change_permission(self, request: HttpRequest, obj: BatchEvent | None = None) -> bool:
        """BatchEvents are immutable."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: BatchEvent | None = None) -> bool:
        """BatchEvents should not be deleted manually."""
        return False
