"""Tests for plugin API router mount resolution + dedup guard.

Covers resolve_plugin_mounts(): two plugins resolving to the same
`/plugins/<label>/` mount prefix is a hard error rather than a silent overwrite.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from tap_api.api import resolve_plugin_mounts


class _FakePluginConfig:
    """Duck-typed stand-in for a TapPluginConfig (label/verbose_name/router)."""

    def __init__(self, label: str, router: object | None, verbose_name: str | None = None):
        self.label = label
        self.verbose_name = verbose_name
        self._router = router

    def get_api_router(self) -> object | None:
        return self._router


def test_distinct_labels_resolve_to_distinct_prefixes():
    configs = [
        _FakePluginConfig("alpha", object(), verbose_name="Alpha"),
        _FakePluginConfig("beta", object()),
    ]
    mounts = resolve_plugin_mounts(configs)
    prefixes = {prefix for prefix, _router, _tag in mounts}
    assert prefixes == {"/plugins/alpha/", "/plugins/beta/"}


def test_router_none_is_skipped():
    configs = [
        _FakePluginConfig("alpha", object()),
        _FakePluginConfig("no_router", None),
    ]
    mounts = resolve_plugin_mounts(configs)
    assert {prefix for prefix, _r, _t in mounts} == {"/plugins/alpha/"}


def test_verbose_name_used_as_tag_else_label():
    configs = [
        _FakePluginConfig("alpha", object(), verbose_name="Alpha Plugin"),
        _FakePluginConfig("beta", object()),
    ]
    tags = {prefix: tag for prefix, _r, tag in resolve_plugin_mounts(configs)}
    assert tags["/plugins/alpha/"] == "Alpha Plugin"
    assert tags["/plugins/beta/"] == "beta"


def test_duplicate_mount_prefix_raises():
    configs = [
        _FakePluginConfig("dup", object()),
        _FakePluginConfig("dup", object()),
    ]
    with pytest.raises(ImproperlyConfigured) as exc:
        resolve_plugin_mounts(configs)
    assert "/plugins/dup/" in str(exc.value)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
