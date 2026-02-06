"""TAP Web application configuration."""

from django.apps import AppConfig


class TapWebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_web"
    verbose_name = "TAP Web"
