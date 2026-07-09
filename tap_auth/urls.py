"""tap_auth URL configuration — mounted at ``/auth/`` by ``tap/urls.py``.

tap_auth owns the auth routes (req-tap-auth-app-3): the allauth machinery
(login, logout, social/OIDC login + callback) plus TAP-specific auth surfaces.
allauth's URLConf is included WITHOUT a namespace so its global view names
(``account_login``, ``account_logout``, the openid_connect routes) reverse as
allauth expects. The ``/auth`` prefix is reserved against Page slugs via the
AppConfig ``reserved_url_prefixes`` registry (req-tap-auth-app-4).

Resulting top-level paths (under ``/auth/``):
    /auth/passkey/login/                         native passkey login page (LOGIN_URL)
    /auth/passkey/login/options/                 authentication options (POST)
    /auth/passkey/login/verify/                  assertion verify + session (POST)
    /auth/enroll/<public-id>/                    invitation redemption shell (anon)
    /auth/enroll/<public-id>/options/            registration options (POST)
    /auth/enroll/<public-id>/verify/             redeem + bind + login (POST)
    /auth/login/                                 allauth (federated) login
    /auth/logout/                                allauth logout
    /auth/oidc/<provider_id>/login/              OIDC login initiation
    /auth/oidc/<provider_id>/login/callback/     OIDC callback
    /auth/no-access/                             generic no-access landing

The native passkey + enroll routes sit under ``/auth/`` deliberately: it is a
``TAP_LOGIN_EXEMPT_PREFIXES`` entry, so the anonymous invitee / logging-in user is
never bounced to the login wall (req-tap-auth-passkey-enrollment / webauthn-11).
"""

from __future__ import annotations

from django.urls import include, path

from tap_auth import views, views_enroll, views_login

urlpatterns = [
    # Native passkey login (the LOGIN_URL target — first-party, no IdP).
    path("passkey/login/", views_login.login_page, name="passkey_login"),
    path("passkey/login/options/", views_login.login_options, name="passkey_login_options"),
    path("passkey/login/verify/", views_login.login_verify, name="passkey_login_verify"),
    # Anonymous invitation redemption (secret rides the URL fragment).
    path("enroll/<str:public_id>/", views_enroll.enroll_page, name="passkey_enroll"),
    path("enroll/<str:public_id>/options/", views_enroll.enroll_options, name="passkey_enroll_options"),
    path("enroll/<str:public_id>/verify/", views_enroll.enroll_verify, name="passkey_enroll_verify"),
    path("no-access/", views.no_access, name="no_access"),
    path("", include("allauth.urls")),
]
