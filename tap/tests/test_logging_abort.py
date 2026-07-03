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


def test_abort_domain_selects_the_stage(caplog):
    """`domain` is the failing stage the watcher/diagnosis keys off."""
    logger = logging.getLogger("tap.preboot")
    with caplog.at_level(logging.ERROR):
        abort(logger, "migrate", "database migration failed")
    assert f"{ABORT_SENTINEL}: migrate: database migration failed" in caplog.records[0].getMessage()
