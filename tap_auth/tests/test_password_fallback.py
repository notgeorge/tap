"""Password-fallback discoverability on the passkey login page (req-tap-auth-passkey-rollout-5).

The passkey page is `LOGIN_URL`, and its ceremony is usernameless + UV-required +
resident-key-required. That is satisfiable by a platform authenticator *or* by a plugged-in
FIDO2 security key — `AuthenticatorSelectionCriteria` sets no `authenticator_attachment`, so
roaming authenticators are first-class. But a machine with neither has no way forward from
that page, even though `TAP_LOCAL_PASSWORD_ENABLED` defaults True and the account works.

These tests pin the fix and, more importantly, the two properties that make it safe:

* the link's visibility tracks the capability exactly (never a link to a path that refuses,
  never a hidden path that works), and
* the fallback target stays brute-force throttled. That last one is the whole reason the
  fallback is allauth's already-mounted login view rather than a native one — a hand-rolled
  `authenticate()` view would silently drop allauth's `login_failed` limit and put an
  unthrottled password form on the front door.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse


@pytest.fixture
def client_localhost() -> Client:
    """A client whose Host passes ALLOWED_HOSTS.

    Not cosmetic: the default `testserver` host raises `DisallowedHost`, which returns 400
    for every request. A throttle probe run that way reports "never throttled" while having
    never reached the view at all — a scan that reads nothing exits clean.
    """
    return Client(SERVER_NAME="localhost")


@pytest.mark.django_db
class TestPasswordFallbackLink:
    def test_link_rendered_when_local_password_enabled(self, settings, client_localhost):
        settings.TAP_LOCAL_PASSWORD_ENABLED = True
        response = client_localhost.get(reverse("passkey_login"))
        assert response.status_code == 200
        assert reverse("account_login") in response.content.decode()

    def test_link_absent_when_local_password_disabled(self, settings, client_localhost):
        """Visibility must track capability: TapModelBackend refuses password auth
        everywhere when the flag is False, so advertising the path would be a dead end."""
        settings.TAP_LOCAL_PASSWORD_ENABLED = False
        response = client_localhost.get(reverse("passkey_login"))
        assert response.status_code == 200
        assert reverse("account_login") not in response.content.decode()

    def test_link_preserves_next(self, settings, client_localhost):
        """A user bounced off a deep link keeps their destination across the fallback.

        Slashes stay unencoded — Django's `urlencode` filter treats `/` as safe, which
        matches the `?next=/` form the login wall itself emits.
        """
        settings.TAP_LOCAL_PASSWORD_ENABLED = True
        response = client_localhost.get(reverse("passkey_login"), {"next": "/plugins/"})
        assert f'{reverse("account_login")}?next=/plugins/' in response.content.decode()

    def test_page_names_security_keys_as_supported(self, client_localhost):
        """The old copy said "the passkey registered on this device", which misdirects the
        security-key user whose credential is not on the device at all."""
        body = client_localhost.get(reverse("passkey_login")).content.decode().lower()
        assert "security key" in body


@pytest.mark.django_db
class TestLogoutLandsOnTapFrontDoor:
    def test_logout_redirects_to_passkey_page_not_allauth(self, client_localhost):
        """Regression: ACCOUNT_LOGOUT_REDIRECT_URL was "account_login", so every logout
        landed on allauth's federated page — a bare username/password form on a
        zero-provider instance. Front door and back door must agree."""
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username="logout-probe", password="x" * 20)
        client_localhost.force_login(user)
        response = client_localhost.post(reverse("account_logout"))
        assert response.status_code == 302
        assert response.url == reverse("passkey_login")


@pytest.mark.django_db
class TestFallbackStaysThrottled:
    def test_repeated_failures_are_rate_limited(self, client_localhost):
        """The security precondition for pointing users at this view.

        allauth signals the `login_failed` limit by re-rendering the form with a message,
        NOT by returning 429 — asserting on status alone reports "not throttled" against a
        view that is throttling correctly. Measured threshold is the 6th attempt, matching
        the configured `login_failed: 5/300s/key`.
        """
        cache.clear()
        url = reverse("account_login")
        throttled_at = None
        for attempt in range(1, 11):
            response = client_localhost.post(url, {"login": "nosuchuser", "password": "wrong-password-attempt"})
            if "too many" in response.content.decode("utf8", "replace").lower():
                throttled_at = attempt
                break
        assert throttled_at is not None, "password fallback is NOT rate limited — do not link to it"
        assert throttled_at <= 6
