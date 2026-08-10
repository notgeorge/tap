"""Tests for the reserved ABORT logging signal (`req-tap-logging-abort-signal`).

The signal is the machine-detectable "fatal, stop waiting" event a watcher
(`scripts/spawn-session.sh` Step 5, `scripts/gate-lean`) fast-fails on. These tests
pin the two properties watchers depend on: the greppable `TAP-ABORT:` rendering
carries the domain + reason, and emitting the signal does NOT itself exit (control
flow stays explicit at the call site).
"""

from __future__ import annotations

import logging

from tap.logging import ABORT_SENTINEL, abort


def test_abort_emits_greppable_sentinel_with_domain_and_reason(caplog):
    """One ERROR record whose message renders the `TAP-ABORT: <domain>: <reason>`
    line a shell watcher greps for — attributed to the caller's logger."""
    logger = logging.getLogger("tap_grid.some_module")
    with caplog.at_level(logging.ERROR):
        abort(logger, "preboot", "core import leak: No module named 'boto3'")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.ERROR
    # Attributed to the caller's component, not tap.logging.
    assert record.name == "tap_grid.some_module"

    message = record.getMessage()
    # The exact substring `scripts/spawn-session.sh` / `gate-lean` grep for.
    assert f"{ABORT_SENTINEL}: preboot: core import leak" in message
    # Guard against the sentinel constant drifting from the helper's literal.
    assert ABORT_SENTINEL == "TAP-ABORT"
    assert f"{ABORT_SENTINEL}:" in message


def test_abort_does_not_raise_or_exit():
    """`abort()` emits the record and returns — the caller owns the raise/exit."""
    # Would raise/SystemExit if the helper tried to exit itself.
    abort(logging.getLogger("tap_boot.orchestrator"), "boot", "population step failed: seed-plugin foo")


def test_abort_detail_rides_message_data_not_the_console_line(caplog):
    """Structured `detail` nests under message_data["detail"] (req-boot-obs-abort-detail-2);
    the rendered TAP-ABORT line stays the one-line sentinel watchers grep."""
    logger = logging.getLogger("tap_boot.management.commands.boot")
    checks = [{"collector": "github_core:github_core", "code": "API_REACHABLE", "status": "fail", "message": "401"}]
    with caplog.at_level(logging.ERROR):
        abort(logger, "boot", "Population step failed", detail={"failed_step": "preflight", "failing_checks": checks})

    record = caplog.records[0]
    assert record.message_data["domain"] == "boot"
    assert record.message_data["detail"]["failed_step"] == "preflight"
    assert record.message_data["detail"]["failing_checks"][0]["code"] == "API_REACHABLE"
    # One-line rendering: the detail payload does not leak into the console line.
    assert "API_REACHABLE" not in record.getMessage()
    assert f"{ABORT_SENTINEL}: boot: Population step failed" in record.getMessage()


def test_abort_without_detail_keeps_legacy_shape(caplog):
    """Callers that pass no detail get exactly the pre-existing message_data shape."""
    with caplog.at_level(logging.ERROR):
        abort(logging.getLogger("tap.preboot"), "preboot", "install failed")
    assert caplog.records[0].message_data == {"domain": "preboot", "reason": "install failed"}


def test_abort_domain_selects_the_stage(caplog):
    """`domain` is the failing stage the watcher/diagnosis keys off."""
    logger = logging.getLogger("tap.preboot")
    with caplog.at_level(logging.ERROR):
        abort(logger, "migrate", "database migration failed")
    assert f"{ABORT_SENTINEL}: migrate: database migration failed" in caplog.records[0].getMessage()
