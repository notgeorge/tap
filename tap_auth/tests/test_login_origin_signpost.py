"""Wrong-origin signpost on the passkey login page (req-tap-auth-passkey-rollout-6).

The ceremony origin is pinned EXACTLY (scheme+host+port, req-tap-auth-passkey-webauthn-7),
and dev sessions are also reachable at the labeled ``<session>.tap.localhost`` alias
(req-dev-multisession-browser-disambiguation) — an origin where the browser rejects
RP-ID ``localhost`` before any prompt appears. On such an origin the button can never
work, so the page must say so BEFORE the click and link the same login URL on the
pinned origin, instead of a dead button and a post-hoc SecurityError message.

Also pinned here: the visibility regression that made the original failure silent.
``auth.css`` hides allauth's classless signup-invite paragraph with a direct-child
selector; without a ``:not([class])`` guard that rule also blanked every TAP-authored
paragraph on the passkey page — including the ``#status`` element that every failure
message writes into, which is precisely how "the button does nothing" shipped.
"""

from __future__ import annotations

import pytest
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse


@pytest.fixture
def client_labeled_origin() -> Client:
    """A client arriving via the labeled ``*.tap.localhost`` session alias — allowed by
    ALLOWED_HOSTS (leading-dot ``.localhost``), refused by the passkey ceremony (its
    origin ``http://testing.tap.localhost`` ≠ test_settings' ``http://localhost:8090``)."""
    return Client(SERVER_NAME="testing.tap.localhost")


@pytest.mark.django_db
class TestWrongOriginSignpost:
    def test_labeled_origin_gets_signpost_with_canonical_link(self, client_labeled_origin):
        """The link is the full request path replayed on the pinned origin, so `next`
        survives (percent-encoded, exactly as the query string arrived)."""
        response = client_labeled_origin.get(reverse("passkey_login"), {"next": "/plugins/"})
        assert response.status_code == 200
        body = response.content.decode()
        assert "tap-auth-banner" in body
        assert "http://localhost:8090/auth/passkey/login/?next=%2Fplugins%2F" in body

    def test_pinned_origin_gets_no_signpost(self, settings):
        """Exact-origin match (scheme+host+port, mirroring verify) renders no banner.
        The client's origin is ``http://localhost`` (test-client port 80 is elided from
        Host), so the pin is aligned to it rather than fighting client port defaults."""
        settings.TAP_PASSKEY_ORIGIN = "http://localhost"
        response = Client(SERVER_NAME="localhost").get(reverse("passkey_login"))
        assert response.status_code == 200
        assert "tap-auth-banner" not in response.content.decode()

    def test_unset_origin_renders_page_without_signpost(self, settings):
        """A misconfigured instance must not 500 the login page itself: the ceremony
        endpoints raise their own ImproperlyConfigured, and the page stays neutral."""
        settings.TAP_PASSKEY_ORIGIN = ""
        response = Client(SERVER_NAME="localhost").get(reverse("passkey_login"))
        assert response.status_code == 200
        assert "tap-auth-banner" not in response.content.decode()


class TestCardParagraphVisibility:
    def test_card_paragraphs_are_not_blanked_by_the_allauth_hide_rule(self):
        """The ``:not([class])`` guard on the invite-hiding rule is load-bearing.

        CSS is not applied in this suite, so this is a content pin, deliberately: the
        unguarded selector ``.tap-auth-card > p`` out-specifies ``.tap-auth-sub`` and
        display:none's the passkey page's intro copy, its ``#status`` line (failure
        messages write into an invisible element), and the password-fallback link.
        That shipped and read as "clicking the button does nothing". If this test
        fails, re-verify the passkey login page IN A BROWSER before adjusting it.
        """
        css_path = finders.find("tap_web/css/auth.css")
        assert css_path, "auth.css not found via staticfiles finders"
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        assert ".tap-auth-card > p:not([class])" in css
        assert ".tap-auth-card > p {" not in css
