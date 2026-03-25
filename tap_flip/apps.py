"""tap_flip Django app configuration."""

from django.apps import AppConfig


class TapFlipConfig(AppConfig):
    """Configuration for the tap_flip provenance and history app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_flip"
    verbose_name = "TAP FLIP"

    def ready(self) -> None:
        """App ready hook — signal-based batch recording has been removed.

        Batch provenance is now driven by CallerContext flowing through the
        service layer into BaseModel.save(). See req-grid-service-batch-signals.
        """
