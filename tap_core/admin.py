"""TAP Core Admin — registers Entity, EntityType, Edge, User."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from tap_core.models import Edge, Entity, EntityType, User

admin.site.register(User, UserAdmin)


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["id", "entity_type", "display_name", "created_at"]
    list_filter = ["entity_type", "created_at"]
    search_fields = ["display_name", "entity_type"]
    readonly_fields = ["id", "created_at", "updated_at", "originating_grid_id"]
    ordering = ["-created_at"]


@admin.register(EntityType)
class EntityTypeAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["slug", "display_name", "icon", "plugin_name"]
    list_filter = ["plugin_name"]
    search_fields = ["slug", "display_name"]


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["id", "from_entity", "edge_type", "to_entity", "created_at"]
    list_filter = ["edge_type", "created_at"]
    search_fields = ["edge_type"]
    readonly_fields = ["id", "created_at", "updated_at", "originating_grid_id"]
    raw_id_fields = ["entity", "from_entity", "to_entity"]
