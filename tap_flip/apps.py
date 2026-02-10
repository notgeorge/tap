"""tap_flip Django app configuration."""

from django.apps import AppConfig


class TapFlipConfig(AppConfig):
    """Configuration for the tap_flip provenance and history app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_flip"
    verbose_name = "TAP FLIP"

    def ready(self) -> None:
        """Connect batch signals when app is ready."""
        import tap_flip.batch.signals  # noqa: F401
