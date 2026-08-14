"""Enrollment-link origin is the ceremony's origin (req-tap-auth-passkey-enrollment-9).

The two enrollment commands each carried their own base-URL derivation,
``TAP_PASSKEY_ORIGIN or TAP_BASE_URL or "http://localhost:8000"`` — and every
branch past the first was guaranteed to mint a DEAD link: those branches only run
when ``TAP_PASSKEY_ORIGIN`` is unset, which is exactly what makes
``expected_origins()`` raise. These tests pin the collapse: one derivation, no
fallbacks, and a mismatched ``--base-url`` refused at mint time rather than
shipped as a link that cannot complete.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from tap_auth.passkey import config as passkey_config

pytestmark = pytest.mark.django_db


class TestEnrollmentBaseUrl:
    @override_settings(TAP_PASSKEY_ORIGIN="https://tap.example.com")
    def test_is_exactly_the_ceremony_origin(self):
        assert passkey_config.enrollment_base_url() == passkey_config.expected_origins()[0]

    @override_settings(TAP_PASSKEY_ORIGIN="", TAP_BASE_URL="https://labelled.example.com")
    def test_does_not_fall_back_to_tap_base_url(self):
        # The old chain would have minted at TAP_BASE_URL — a link the ceremony
        # rejects, because an unset TAP_PASSKEY_ORIGIN makes it raise.
        with pytest.raises(ImproperlyConfigured, match="TAP_PASSKEY_ORIGIN"):
            passkey_config.enrollment_base_url()

    @override_settings(TAP_PASSKEY_ORIGIN="", TAP_BASE_URL="")
    def test_does_not_fall_back_to_localhost(self):
        with pytest.raises(ImproperlyConfigured, match="TAP_PASSKEY_ORIGIN"):
            passkey_config.enrollment_base_url()


class TestAssertEnrollmentOrigin:
    @override_settings(TAP_PASSKEY_ORIGIN="https://tap.example.com")
    def test_matching_origin_passes(self):
        passkey_config.assert_enrollment_origin("https://tap.example.com")

    @override_settings(TAP_PASSKEY_ORIGIN="https://tap.example.com")
    def test_trailing_slash_and_case_are_not_a_mismatch(self):
        # Origin comparison is scheme+host+port; cosmetic differences must not
        # trip an operator who is otherwise correct.
        passkey_config.assert_enrollment_origin("https://TAP.example.com/")

    @override_settings(TAP_PASSKEY_ORIGIN="https://tap.example.com")
    def test_different_host_is_refused(self):
        with pytest.raises(ImproperlyConfigured, match="does not match"):
            passkey_config.assert_enrollment_origin("https://other.example.com")

    @override_settings(TAP_PASSKEY_ORIGIN="https://tap.example.com")
    def test_different_port_is_refused(self):
        with pytest.raises(ImproperlyConfigured, match="does not match"):
            passkey_config.assert_enrollment_origin("https://tap.example.com:8443")

    @override_settings(TAP_PASSKEY_ORIGIN="https://tap.example.com")
    def test_different_scheme_is_refused(self):
        with pytest.raises(ImproperlyConfigured, match="does not match"):
            passkey_config.assert_enrollment_origin("http://tap.example.com")


class TestCommandsRefuseRatherThanMintDeadLinks:
    """Both commands surface the refusal as a clean CommandError, not a traceback."""

    @override_settings(TAP_PASSKEY_ORIGIN="", TAP_BASE_URL="https://labelled.example.com")
    def test_enroll_admin_refuses_when_origin_unset(self):
        with pytest.raises(CommandError, match="TAP_PASSKEY_ORIGIN"):
            call_command("enroll_admin", "--email", "someone@example.com")

    @override_settings(TAP_PASSKEY_ORIGIN="https://tap.example.com")
    def test_enroll_admin_refuses_mismatched_base_url(self):
        with pytest.raises(CommandError, match="does not match"):
            call_command(
                "enroll_admin",
                "--email",
                "someone@example.com",
                "--base-url",
                "https://elsewhere.example.com",
            )
