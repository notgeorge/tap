"""Tests for the cross-scope-access CONCERN tripwire (req-tap-cares-secrets-cross-scope-concern).

The detective half of the deferred least-privilege enforcement: a plugin resolving
the install-system `tap_plugins.source` scope emits a `security` CONCERN. Narrow v0
— fires only for that zero-false-positive case. A plugin caller is simulated by
exec-ing the call in a namespace whose `__name__` is a `tap_plugin.<slug>` package,
which is what `calling_plugin_slug` reads off the stack.
"""

from __future__ import annotations

import logging
from typing import Any

from tap.logging_signals import CONCERN_MESSAGE_CODE
from tap.plugin_source_auth import SOURCE_SECRET_SCOPE
from tap_cares.exceptions import SecretNotFoundError
from tap_cares.secrets import SecretRef, resolve_secret


def _resolve_from_plugin_frame(scope: str, key: str) -> None:
    """Call resolve_secret from a frame whose module looks like a plugin package."""
    ns = {
        "__name__": "tap_plugin.evilplugin.collectors.thief",
        "resolve_secret": resolve_secret,
        "SecretRef": SecretRef,
        "scope": scope,
        "key": key,
    }
    exec("def _grab():\n    return resolve_secret(SecretRef(scope=scope, key=key))", ns)
    # exec-built callable; ns is dict[str, object], so mypy sees `object` here.
    grab = ns["_grab"]
    try:
        grab()  # type: ignore[operator]
    except SecretNotFoundError:
        pass  # the tripwire fires BEFORE the lookup; the lookup's outcome is irrelevant


def _concern_records(caplog: Any) -> list[Any]:
    # list[Any] on purpose: elements are Any, so reading the dynamic
    # `.message_code`/`.message_data` LogRecord attrs stays clean (and the typed
    # signature avoids the strict no-untyped-call at the call sites).
    return [r for r in caplog.records if getattr(r, "message_code", None) == CONCERN_MESSAGE_CODE]


def test_plugin_resolving_install_scope_emits_concern(caplog):
    with caplog.at_level(logging.WARNING):
        _resolve_from_plugin_frame(SOURCE_SECRET_SCOPE, "github-plugins-ro")

    records = _concern_records(caplog)
    assert len(records) == 1
    data = records[0].message_data
    assert data["concern_type"] == "cross_scope_secret_access"
    assert data["tags"] == ["security"]
    message = records[0].getMessage()
    assert "evilplugin" in message  # names the offending plugin
    assert SOURCE_SECRET_SCOPE in message
    assert "github-plugins-ro" in message  # the key name (a reference, not material)


def test_non_plugin_caller_does_not_fire(caplog):
    # This test module is not a tap_plugin.* package → no plugin frame → no concern.
    with caplog.at_level(logging.WARNING):
        try:
            resolve_secret(SecretRef(scope=SOURCE_SECRET_SCOPE, key="github-plugins-ro"))
        except SecretNotFoundError:
            pass
    assert _concern_records(caplog) == []


def test_plugin_resolving_non_install_scope_does_not_fire(caplog):
    # A plugin resolving a non-install scope is normal — the tripwire skips it early
    # (broader plugin-vs-plugin detection is a deliberate fast-follow, not v0).
    with caplog.at_level(logging.WARNING):
        _resolve_from_plugin_frame("github_core", "collector")
    assert _concern_records(caplog) == []
