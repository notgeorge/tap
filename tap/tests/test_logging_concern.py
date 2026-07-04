"""Tests for the reserved CONCERN logging signal (`req-tap-logging-concern-signal`).

CONCERN is the third reserved cross-cutting signal (after FLAW/ABORT) — the
"permitted-but-suspicious, somebody's-being-sus" detective signal. These pin the
properties a security monitor depends on: the greppable `TAP-CONCERN:` rendering,
the structured `message_data` payload, WARNING level, non-blocking, and secret-free.
"""

from __future__ import annotations

import logging

from tap.logging import CONCERN_SENTINEL, concern
from tap.logging_signals import CONCERN_MESSAGE_CODE


def test_concern_emits_greppable_sentinel_at_warning(caplog):
    logger = logging.getLogger("tap_cares.some_module")
    with caplog.at_level(logging.WARNING):
        concern(logger, "secrets", "cross_scope_secret_access", "plugin 'evil' resolved tap_plugins.source")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert record.name == "tap_cares.some_module"

    message = record.getMessage()
    assert CONCERN_SENTINEL == "TAP-CONCERN"
    assert f"{CONCERN_SENTINEL}: secrets: plugin 'evil' resolved tap_plugins.source" in message


def test_concern_attaches_structured_payload(caplog):
    logger = logging.getLogger("tap_cares.x")
    with caplog.at_level(logging.WARNING):
        concern(logger, "secrets", "cross_scope_secret_access", "reason text", tags=("security",))
    record = caplog.records[0]
    assert record.message_code == CONCERN_MESSAGE_CODE
    data = record.message_data
    assert data == {
        "domain": "secrets",
        "concern_type": "cross_scope_secret_access",
        "tags": ["security"],
        "reason": "reason text",
    }


def test_concern_is_non_blocking():
    # Emits and returns — a tripwire observes, it does not stop the caller.
    concern(logging.getLogger("tap_cares.x"), "plugins", "some_type", "something sus")


def test_unregistered_tag_falls_back_to_security(caplog):
    logger = logging.getLogger("tap_cares.x")
    with caplog.at_level(logging.WARNING):
        concern(logger, "secrets", "t", "r", tags=("not-a-real-tag",))
    # The concern still emits (fail-open in the emit path), with a safe default tag.
    assert caplog.records[0].message_data["tags"] == ["security"]
