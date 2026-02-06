"""tap_viz Django app configuration."""

from django.apps import AppConfig


class TapVizConfig(AppConfig):
    """Configuration for the tap_viz visualization app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_viz"
    verbose_name = "TAP Visualization"
