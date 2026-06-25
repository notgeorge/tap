"""tap_auth-owned declaration of the django-allauth INSTALLED_APPS entries.

Django's app registry is flat and frozen during ``django.setup()`` (before any
``AppConfig.ready()`` runs), so allauth's apps MUST be listed in
``settings.INSTALLED_APPS`` — no app can append other apps. But tap_auth can own
the *declaration* and the ordering rationale; ``tap/settings.py`` just spreads
``ALLAUTH_APPS`` into the list. This is the django-oscar "framework exports its
app-list, project assembles it" pattern, applied to the tap_auth integration app
(which owns the adapter, providers, policy, and URL includes; allauth stays a
peer engine, and tap_web owns the templates).

IMPORTANT: this module is imported at settings-build time, BEFORE the app
registry exists. Keep it a bare list constant — no Django model imports, no
``django.conf.settings`` access at module top — or it hits the settings-import
re-entrancy class encountered elsewhere in tap_auth.

Ordering note (enforced by where settings spreads this): allauth must come AFTER
the tap apps so tap_web wins template resolution (APP_DIRS first-match-wins) and
overrides allauth's defaults. The openid_connect provider backs every google_oidc
TAP provider, addressed by a stable provider_id natural key.
"""

from __future__ import annotations

ALLAUTH_APPS: list[str] = [
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.openid_connect",
]
