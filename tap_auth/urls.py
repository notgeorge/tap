"""tap_auth URL configuration — mounted at ``/auth/`` by ``tap/urls.py``.

tap_auth owns the auth routes (req-tap-auth-app-3): the allauth machinery
(login, logout, social/OIDC login + callback) plus TAP-specific auth surfaces.
allauth's URLConf is included WITHOUT a namespace so its global view names
(``account_login``, ``account_logout``, the openid_connect routes) reverse as
allauth expects. The ``/auth`` prefix is reserved against Page slugs via the
AppConfig ``reserved_url_prefixes`` registry (req-tap-auth-app-4).

Resulting top-level paths (under ``/auth/``):
    /auth/login/                                 allauth login
    /auth/logout/                                allauth logout
    /auth/oidc/<provider_id>/login/              OIDC login initiation
    /auth/oidc/<provider_id>/login/callback/     OIDC callback
    /auth/no-access/                             generic no-access landing
"""

from __future__ import annotations

from django.urls import include, path

from tap_auth import views

urlpatterns = [
    path("no-access/", views.no_access, name="no_access"),
    path("", include("allauth.urls")),
]
