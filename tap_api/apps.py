"""TAP API application configuration."""

from django.apps import AppConfig


class TapApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_api"
    verbose_name = "TAP API"

    def ready(self) -> None:
        from tap_api.api import discover_plugin_routers

        discover_plugin_routers()
