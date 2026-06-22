"""tap_auth Django app configuration.

`tap_auth` is TAP's authentication/authorization management plane and the owner
of the canonical `AUTH_USER_MODEL` (req-tap-auth-app, req-tap-auth-user-model).
It loads before `tap_grid` so the swapped user model is a clean dependency root
for every app's first migration (req-tap-auth-user-model-6).

Spec: tap_auth/specs/spec-tap-auth-v0.md
"""

from django.apps import AppConfig


class TapAuthConfig(AppConfig):
    """Configuration for the tap_auth app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_auth"
    verbose_name = "TAP Auth"

    # Top-level URL prefix this app owns (req-tap-auth-app-3/4). Reserved against
    # Page slugs via the registry mechanism in tap_web/reserved.py — declared here
    # so the reservation lives with its owner rather than the project-level list.
    # Routes are not mounted yet (deferred to the allauth phase); the reservation
    # is a forward guard so no Page can occupy /auth before then.
    reserved_url_prefixes: list[str] = ["/auth"]
