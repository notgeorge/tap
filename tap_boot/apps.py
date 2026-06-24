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
