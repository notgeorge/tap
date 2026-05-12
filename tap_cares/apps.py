"""tap_cares application configuration."""

from django.apps import AppConfig


class TapCaresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_cares"
    verbose_name = "TAP Cares"

    def ready(self) -> None:
        # Intentionally empty until the first collector (FedRAMP 20x KSI) lands
        # and needs to register at startup. See tap_cares/specs/spec-tap-cares-v0.md
        # and spec-tap-cares-collector.md.
        return
