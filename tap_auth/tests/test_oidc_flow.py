"""Lightweight in-CI OIDC flow test (increment 3 — the mockoidc-style layer-3).

Drives allauth's real openid_connect login-initiation against a MOCK issuer (the
discovery document is stubbed; no real Google), asserting the redirect to the
IdP's authorization endpoint is correctly assembled from a TAP provider config,
and that POST-only initiation (SOCIALACCOUNT_LOGIN_ON_GET=False) is enforced.

The token-exchange/callback half of the flow lands the user in
``pre_social_login`` → ``evaluate_access`` → provisioning, which is exercised
directly and exhaustively in test_adapter.py (the security decisions). Real
Google end-to-end is the manual browser smoke.
"""

from __future__ import annotations

import urllib.parse as urlparse
from unittest import mock

import pytest
from django.test import Client

_IDP = "https://idp.example.test"
_DISCOVERY = {
    "issuer": _IDP,
    "authorization_endpoint": f"{_IDP}/authorize",
    "token_endpoint": f"{_IDP}/token",
    "jwks_uri": f"{_IDP}/jwks",
    "userinfo_endpoint": f"{_IDP}/userinfo",
}

_APPS = {
    "openid_connect": {
        "APPS": [
            {
                "provider_id": "criticalsec-google",
                "name": "criticalsec.com",
                "client_id": "mock-client.apps.googleusercontent.com",
                "secret": "GOCSPX-mock",
                "settings": {"server_url": _IDP},
            }
        ]
    }
}


def _discovery_response():
    resp = mock.Mock()
    resp.status_code = 200
    resp.json.return_value = _DISCOVERY
    resp.ok = True
    return resp


@pytest.mark.django_db
class TestOidcInitiation:
    def test_post_initiation_redirects_to_idp(self, settings):
        settings.SOCIALACCOUNT_PROVIDERS = _APPS
        with mock.patch("requests.Session.get", return_value=_discovery_response()):
            r = Client().post("/auth/oidc/criticalsec-google/login/", SERVER_NAME="localhost")
        assert r.status_code == 302
        loc = r.headers["Location"]
        assert loc.startswith(f"{_IDP}/authorize")
        q = urlparse.parse_qs(urlparse.urlparse(loc).query)
        assert q["client_id"][0] == "mock-client.apps.googleusercontent.com"
        assert q["response_type"][0] == "code"
        assert q["redirect_uri"][0].endswith("/auth/oidc/criticalsec-google/login/callback/")

    def test_get_does_not_initiate(self, settings):
        """LOGIN_ON_GET=False: a GET must not 302 straight to the IdP (login-CSRF
        guard). allauth renders a confirm page instead."""
        settings.SOCIALACCOUNT_PROVIDERS = _APPS
        with mock.patch("requests.Session.get", return_value=_discovery_response()):
            r = Client().get("/auth/oidc/criticalsec-google/login/", SERVER_NAME="localhost")
        assert r.status_code != 302 or not r.headers.get("Location", "").startswith(_IDP)
