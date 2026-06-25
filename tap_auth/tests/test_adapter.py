"""Social adapter + ExternalIdentity tests (increment 3 — req-tap-auth-google-oidc,
req-tap-auth-external-identity).

Layer-1 of the OIDC test strategy: the security decision (``evaluate_access``)
is a pure function exercised exhaustively with synthetic claims (no network, no
DB), and the adapter's gate/provisioning logic is tested directly. Real-Google
end-to-end is the manual smoke.
"""

from __future__ import annotations

import pytest
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory

from tap_auth.adapter import TapSocialAccountAdapter
from tap_auth.models import ExternalIdentity, ExternalIdentityStatus
from tap_auth.providers import ProviderConfig, get_provider

PROVIDER_ID = "criticalsec-google"


def _provider_raw(**over) -> dict:
    raw = {
        "id": PROVIDER_ID,
        "type": "google_oidc",
        "display_name": "criticalsec.com (Google)",
        "allowed_domains": ["criticalsec.com"],
    }
    raw.update(over)
    return raw


def _claims(**over) -> dict:
    c = {
        "sub": "google-sub-123",
        "email": "george@criticalsec.com",
        "email_verified": True,
        "hd": "criticalsec.com",
        "name": "George",
    }
    c.update(over)
    return c


def _eval(provider_raw: dict, claims: dict):
    cfg = ProviderConfig.from_dict(provider_raw)
    return get_provider(cfg.type).evaluate_access(cfg, claims)


# --------------------------------------------------------------------------- #
# evaluate_access — the pure security core
# --------------------------------------------------------------------------- #


class TestEvaluateAccess:
    def test_allow_verified_in_domain_and_allowlist(self):
        d = _eval(_provider_raw(allowed_emails=["george@criticalsec.com"]), _claims())
        assert d.allowed is True
        assert d.matched_domain == "criticalsec.com"
        assert d.verified_email == "george@criticalsec.com"

    def test_allow_domain_only_no_allowlist(self):
        assert _eval(_provider_raw(), _claims()).allowed is True

    def test_deny_email_not_verified(self):
        d = _eval(_provider_raw(), _claims(email_verified=False))
        assert d.allowed is False and d.reason == "email_not_verified"

    def test_email_verified_string_true_accepted(self):
        assert _eval(_provider_raw(), _claims(email_verified="true")).allowed is True

    def test_deny_domain_not_allowed_by_hd(self):
        d = _eval(_provider_raw(), _claims(hd="evil.com", email="x@evil.com"))
        assert d.allowed is False and d.reason == "domain_not_allowed"

    def test_deny_no_hd_no_fallback(self):
        # consumer Google account: no hd, fallback off → denied (no silent email-domain match)
        c = _claims(email="george@criticalsec.com")
        c.pop("hd")
        d = _eval(_provider_raw(), c)
        assert d.allowed is False and d.reason == "domain_not_allowed"

    def test_allow_via_email_domain_fallback_when_enabled(self):
        c = _claims(email="george@criticalsec.com")
        c.pop("hd")
        d = _eval(_provider_raw(email_domain_fallback=True), c)
        assert d.allowed is True and d.matched_domain == "criticalsec.com"

    def test_fallback_still_requires_verified_email(self):
        c = _claims(email="george@criticalsec.com", email_verified=False)
        c.pop("hd")
        d = _eval(_provider_raw(email_domain_fallback=True), c)
        assert d.allowed is False and d.reason == "email_not_verified"

    def test_deny_account_not_allowlisted(self):
        d = _eval(_provider_raw(allowed_emails=["someone-else@criticalsec.com"]), _claims())
        assert d.allowed is False and d.reason == "account_not_allowlisted"

    def test_hd_takes_precedence_over_email_domain(self):
        # hd is the trustworthy claim; an attacker-controlled email domain must not widen access
        d = _eval(
            _provider_raw(allowed_domains=["criticalsec.com"]), _claims(hd="criticalsec.com", email="george@gmail.com")
        )
        # email domain (gmail.com) is NOT allowed, but hd (criticalsec.com) IS → matched on hd
        assert d.allowed is True and d.matched_domain == "criticalsec.com"


# --------------------------------------------------------------------------- #
# ExternalIdentity model
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
class TestExternalIdentityModel:
    def test_redacted_subject_hides_full_value(self):
        u = get_user_model().objects.create_user(username="u1")
        ei = ExternalIdentity.objects.create(
            provider_id=PROVIDER_ID, provider_type="google_oidc", subject="super-secret-sub", user=u
        )
        assert "super-secret-sub" not in ei.redacted_subject
        assert ei.redacted_subject.startswith("sub#")

    def test_generate_username_stable_and_prefixed(self):
        a = ExternalIdentity.generate_username(PROVIDER_ID, "sub-1")
        b = ExternalIdentity.generate_username(PROVIDER_ID, "sub-1")
        assert a == b and a.startswith(f"ext-{PROVIDER_ID}-") and len(a) <= 150

    def test_provider_subject_unique(self):
        from django.db import IntegrityError

        u = get_user_model().objects.create_user(username="u2")
        ExternalIdentity.objects.create(provider_id=PROVIDER_ID, provider_type="google_oidc", subject="dup", user=u)
        with pytest.raises(IntegrityError):
            ExternalIdentity.objects.create(provider_id=PROVIDER_ID, provider_type="google_oidc", subject="dup", user=u)


# --------------------------------------------------------------------------- #
# Social adapter — gate + provisioning
# --------------------------------------------------------------------------- #


def _sociallogin(claims: dict, *, is_existing: bool = False) -> SocialLogin:
    account = SocialAccount(provider=PROVIDER_ID, uid=claims["sub"], extra_data=claims)
    sl = SocialLogin(account=account)
    sl.user = get_user_model()(username="pending", email=claims.get("email", ""))
    sl.state = {}
    # is_existing is a property on SocialLogin derived from account.pk; emulate it
    sl.account.pk = 1 if is_existing else None
    return sl


@pytest.mark.django_db
class TestSocialAdapter:
    def _request(self):
        return RequestFactory().get("/auth/oidc/criticalsec-google/login/callback/")

    def test_pre_social_login_allows_valid(self, settings):
        settings.TAP_AUTH_PROVIDERS = [_provider_raw(allowed_emails=["george@criticalsec.com"])]
        # no raise == allowed
        TapSocialAccountAdapter().pre_social_login(self._request(), _sociallogin(_claims()))

    def test_pre_social_login_denies_wrong_domain(self, settings):
        settings.TAP_AUTH_PROVIDERS = [_provider_raw()]
        with pytest.raises(ImmediateHttpResponse) as exc:
            TapSocialAccountAdapter().pre_social_login(
                self._request(), _sociallogin(_claims(hd="evil.com", email="x@evil.com"))
            )
        assert exc.value.response.status_code == 403
        assert b"domain_not_allowed" in exc.value.response.content

    def test_pre_social_login_denies_not_allowlisted(self, settings):
        settings.TAP_AUTH_PROVIDERS = [_provider_raw(allowed_emails=["only@criticalsec.com"])]
        with pytest.raises(ImmediateHttpResponse) as exc:
            TapSocialAccountAdapter().pre_social_login(self._request(), _sociallogin(_claims()))
        assert b"account_not_allowlisted" in exc.value.response.content

    def test_pre_social_login_denies_unknown_provider(self, settings):
        settings.TAP_AUTH_PROVIDERS = []  # no config for this provider id
        with pytest.raises(ImmediateHttpResponse):
            TapSocialAccountAdapter().pre_social_login(self._request(), _sociallogin(_claims()))

    def test_pre_social_login_denies_linking_same_email(self, settings):
        settings.TAP_AUTH_PROVIDERS = [_provider_raw()]
        # an existing user already holds this email
        get_user_model().objects.create_user(username="existing", email="george@criticalsec.com")
        with pytest.raises(ImmediateHttpResponse) as exc:
            TapSocialAccountAdapter().pre_social_login(self._request(), _sociallogin(_claims(), is_existing=False))
        assert b"identity_linking_disabled" in exc.value.response.content

    def test_is_auto_signup_follows_policy(self, settings):
        settings.TAP_AUTH_PROVIDERS = [_provider_raw(auto_provision=False)]
        assert TapSocialAccountAdapter().is_auto_signup_allowed(self._request(), _sociallogin(_claims())) is False
        settings.TAP_AUTH_PROVIDERS = [_provider_raw(auto_provision=True)]
        assert TapSocialAccountAdapter().is_auto_signup_allowed(self._request(), _sociallogin(_claims())) is True

    def test_sync_external_identity_creates_record(self, settings):
        settings.TAP_AUTH_PROVIDERS = [_provider_raw()]
        user = get_user_model().objects.create_user(username="pending")
        sl = _sociallogin(_claims())
        TapSocialAccountAdapter()._sync_external_identity(sl, user)
        ei = ExternalIdentity.objects.get(provider_id=PROVIDER_ID, subject="google-sub-123")
        assert ei.user_id == user.pk
        assert ei.email_snapshot == "george@criticalsec.com"
        assert ei.hosted_domain_snapshot == "criticalsec.com"
        assert ei.status == ExternalIdentityStatus.ACTIVE
        user.refresh_from_db()
        assert user.username.startswith(f"ext-{PROVIDER_ID}-")
        assert user.email == "george@criticalsec.com"

    def test_apply_initial_admin_grants_group(self, settings):
        settings.TAP_AUTH_PROVIDERS = [_provider_raw()]
        settings.TAP_AUTH_INITIAL_ADMINS = ["george@criticalsec.com"]
        Group.objects.get_or_create(name="tap_admin")
        user = get_user_model().objects.create_user(username="g", email="george@criticalsec.com")
        TapSocialAccountAdapter()._apply_initial_admin(user)
        assert user.groups.filter(name="tap_admin").exists()

    def test_apply_initial_admin_skips_non_declared(self, settings):
        settings.TAP_AUTH_INITIAL_ADMINS = ["someone@criticalsec.com"]
        Group.objects.get_or_create(name="tap_admin")
        user = get_user_model().objects.create_user(username="h", email="other@criticalsec.com")
        TapSocialAccountAdapter()._apply_initial_admin(user)
        assert not user.groups.filter(name="tap_admin").exists()
