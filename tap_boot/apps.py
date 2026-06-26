"""tap_boot application configuration.

``tap_boot`` owns no models and writes nothing at ``ready()`` time — it is a
pure management-plane app (the ``manage.py boot`` command + the orchestrator it
calls). It sits first in ``INSTALLED_APPS`` so that, when the section-handler
registry is built (deferred, req-boot-sections), nothing below boot imports it;
in v0 the first position is harmless because the app contributes no migrations
and resolves the swapped user model the same as every other app.
"""

from django.apps import AppConfig


class TapBootConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_boot"
    verbose_name = "TAP Boot"

    def ready(self) -> None:
        """Register tap_boot's startup system checks.

        Importing ``tap_boot.checks`` only *registers* the check functions with
        Django's system check framework; the DB access they perform happens
        later, when the checks run (during ``migrate`` / ``check --database``).
        So this stays within TAP's "no DB access in ``ready()``" rule.
        """
        from tap_boot import checks  # noqa: F401  (import registers the checks)
