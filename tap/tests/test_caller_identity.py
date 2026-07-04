"""Tests for best-effort plugin caller identity (tap/caller_identity.py).

Used by the plugin-safety CONCERN tripwires to answer "which plugin, if any, is
on the stack?". Best-effort and evadable by design; these pin the parsing and the
"no plugin frame ⇒ None" contract. The positive stack-walk case is exercised
end-to-end by the cross-scope-concern tripwire test.
"""

from __future__ import annotations

from tap.caller_identity import _slug_from_module, calling_plugin_slug


def test_slug_from_plugin_module() -> None:
    assert _slug_from_module("tap_plugin.github_core.collectors.x") == "github_core"
    assert _slug_from_module("tap_plugin.fedramp_20x_ksi") == "fedramp_20x_ksi"


def test_slug_from_non_plugin_module_is_none() -> None:
    assert _slug_from_module("tap_cares.secrets.registry") is None
    assert _slug_from_module("tap_plugins.validate.service") is None  # the app, not a plugin package
    assert _slug_from_module("") is None
    assert _slug_from_module("tap_plugin") is None  # bare namespace, no slug
    assert _slug_from_module("tap_plugin.") is None


def test_calling_plugin_slug_none_from_test_module() -> None:
    # This test module is not under tap_plugin.*, and neither is anything above it
    # on the stack, so there is no plugin frame to find.
    assert calling_plugin_slug() is None
