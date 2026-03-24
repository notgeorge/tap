from django.apps import AppConfig


class TapCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_grid"
    verbose_name = "TAP Core"

    def ready(self) -> None:
        from django.db import OperationalError, ProgrammingError

        try:
            from tap_grid.models import EntityType

            EntityType.objects.get_or_create(
                slug="search",
                defaults={"name": "Search", "plugin_name": "tap_grid", "icon": "search"},
            )
        except (OperationalError, ProgrammingError):
            # DB not ready yet (e.g. during initial migrate).
            pass
