"""TAP API application configuration."""

from django.apps import AppConfig


class TapApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_api"
    verbose_name = "TAP API"

    # Top-level URL prefix this app mounts (tap/urls.py), reserved against Page
    # slugs. Collected by tap_web.reserved.get_reserved_url_prefixes().
    reserved_url_prefixes: list[str] = ["/api"]

    def ready(self) -> None:
        from tap_api.api import discover_plugin_routers

        discover_plugin_routers()
