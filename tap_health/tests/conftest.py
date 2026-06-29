"""Shared fixtures for tap_health tests."""

from __future__ import annotations

import pytest

from tap_health.registry import health_probe_registry


@pytest.fixture
def isolated_probe_registry():
    """Snapshot/restore the global probe registry around a test.

    `run_health()` and `register_health_probe()` operate on the process-wide
    `health_probe_registry` (populated by app `ready()` hooks). Tests that
    register their own probes reset it to empty and restore the real set after.
    """
    saved = health_probe_registry.all()
    health_probe_registry._reset_for_testing()
    yield health_probe_registry
    health_probe_registry._reset_for_testing(saved)
