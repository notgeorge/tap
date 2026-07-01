"""Tests for the Flaw mechanism (spec-tap-flaw-v0.md, focused v0 slice).

Covers the Flaw hierarchy, the registered domain-tag vocabulary, the single
emission path (`report`), severity-from-handling, the unknown-tag/misuse →
`code` Flaw rule, and the wired `app` Flaw instance (plugin mount collision).

No DB needed — pure logging behavior — so these run without the test database.
"""

from __future__ import annotations

import logging

import pytest
from django.core.exceptions import ImproperlyConfigured

from tap.flaws import (
    FLAW_TAGS,
    HANDLING_ABORT_OPERATION,
    HANDLING_FAIL_CLOSED_CONTINUE,
    HANDLING_REFUSE_BOOT,
    AppFlaw,
    CodeFlaw,
    Flaw,
    InstanceFlaw,
    flaw_class_for_path,
    report_service_layer_bypass,
)


class _Capture(logging.Handler):
    """Collects emitted LogRecords regardless of logger propagation config."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured_logger():
    """A logger with an attached capture handler; yields (logger, handler)."""
    logger = logging.getLogger("tap.tests.flaws")
    logger.setLevel(logging.DEBUG)
    handler = _Capture()
    logger.addHandler(handler)
    try:
        yield logger, handler
    finally:
        logger.removeHandler(handler)


def _flaw_records(handler: _Capture) -> list[logging.LogRecord]:
    return [r for r in handler.records if getattr(r, "message_code", None) == "FLAW"]


# ---------------------------------------------------------------------------
# Hierarchy (req-flaw-concept, req-flaw-classes)
# ---------------------------------------------------------------------------


def test_subclass_blame_classes():
    assert CodeFlaw.flaw_class == "code"
    assert AppFlaw.flaw_class == "app"
    assert InstanceFlaw.flaw_class == "instance"


def test_flaws_are_exceptions():
    flaw = AppFlaw(invariant_id="x", tags=["integration"], handling=HANDLING_ABORT_OPERATION, message="m")
    assert isinstance(flaw, Exception)


def test_message_data_shape():
    flaw = InstanceFlaw(
        invariant_id="capability_sync_drift",
        tags=["security", "config"],
        handling=HANDLING_ABORT_OPERATION,
        message="drift",
        context={"declared": 3},
    )
    md = flaw.message_data()
    assert md["flaw_class"] == "instance"
    assert md["flaw_tags"] == ["security", "config"]
    assert md["invariant_id"] == "capability_sync_drift"
    assert md["handling"] == HANDLING_ABORT_OPERATION
    assert md["context"] == {"declared": 3}


def test_base_flaw_cannot_be_reported():
    with pytest.raises(TypeError):
        Flaw.report(
            invariant_id="x",
            tags=["operational"],
            handling=HANDLING_ABORT_OPERATION,
            message="m",
            logger=logging.getLogger("tap.tests.flaws"),
        )


# ---------------------------------------------------------------------------
# Emission (req-flaw-emission)
# ---------------------------------------------------------------------------


def test_report_emits_structured_flaw(captured_logger):
    logger, handler = captured_logger
    returned = CodeFlaw.report(
        invariant_id="unguarded_operation",
        tags=["security"],
        handling=HANDLING_FAIL_CLOSED_CONTINUE,
        message="no authorize() recorded",
        logger=logger,
    )
    flaws = _flaw_records(handler)
    assert len(flaws) == 1
    rec = flaws[0]
    assert rec.message_code == "FLAW"
    assert rec.message_data["flaw_class"] == "code"
    assert rec.message_data["flaw_tags"] == ["security"]
    assert rec.message_data["invariant_id"] == "unguarded_operation"
    assert rec.message_data["handling"] == HANDLING_FAIL_CLOSED_CONTINUE
    # report() returns the instance so the caller may raise it.
    assert isinstance(returned, CodeFlaw)


def test_report_returns_raisable_instance(captured_logger):
    logger, _ = captured_logger
    with pytest.raises(AppFlaw):
        raise AppFlaw.report(
            invariant_id="x",
            tags=["integration"],
            handling=HANDLING_REFUSE_BOOT,
            message="m",
            logger=logger,
        )


def test_context_kwargs_ride_message_data(captured_logger):
    logger, handler = captured_logger
    AppFlaw.report(
        invariant_id="plugin_mount_collision",
        tags=["integration"],
        handling=HANDLING_REFUSE_BOOT,
        message="dup",
        logger=logger,
        prefix="/plugins/dup/",
    )
    rec = _flaw_records(handler)[0]
    assert rec.message_data["context"]["prefix"] == "/plugins/dup/"


# ---------------------------------------------------------------------------
# Service-layer-bypass helper — class-aware emitter for the grid guards
# ---------------------------------------------------------------------------


def test_flaw_class_for_path_plugin_is_app():
    assert flaw_class_for_path("/app/plugins/lotr/editors/character.py") is AppFlaw


def test_flaw_class_for_path_first_party_is_code():
    assert flaw_class_for_path("/app/tap_web/views.py") is CodeFlaw


def test_flaw_class_for_path_unknown_is_code():
    """A missing/unknown path defaults to `code` — TAP core owns the ambiguity."""
    assert flaw_class_for_path(None) is CodeFlaw


def test_report_service_layer_bypass_emits_security_flaw(captured_logger):
    logger, handler = captured_logger
    flaw = report_service_layer_bypass(
        invariant_id="grid_write_service_layer_bypass",
        message="unguarded write: save tap_web.Panel bypassed the service layer",
        logger=logger,
    )
    rec = _flaw_records(handler)[0]
    assert rec.message_data["flaw_tags"] == ["security"]
    assert rec.message_data["invariant_id"] == "grid_write_service_layer_bypass"
    assert rec.message_data["handling"] == HANDLING_ABORT_OPERATION
    # The offending callsite is captured for routing; this test frame is
    # first-party, so the blame class is `code`.
    assert rec.message_data["flaw_class"] == "code"
    assert "offending_callsite" in rec.message_data["context"]
    assert isinstance(flaw, CodeFlaw)


# ---------------------------------------------------------------------------
# Severity from handling (req-flaw-severity-orthogonal)
# ---------------------------------------------------------------------------


def test_refuse_boot_is_critical(captured_logger):
    logger, handler = captured_logger
    AppFlaw.report(invariant_id="x", tags=["integration"], handling=HANDLING_REFUSE_BOOT, message="m", logger=logger)
    assert _flaw_records(handler)[0].levelno == logging.CRITICAL


def test_fail_closed_is_error(captured_logger):
    logger, handler = captured_logger
    CodeFlaw.report(
        invariant_id="x", tags=["security"], handling=HANDLING_FAIL_CLOSED_CONTINUE, message="m", logger=logger
    )
    assert _flaw_records(handler)[0].levelno == logging.ERROR


# ---------------------------------------------------------------------------
# Registered vocabulary + misuse → code Flaw (req-flaw-domain-tags, actionable)
# ---------------------------------------------------------------------------


def test_known_tags_have_descriptions():
    for tag, desc in FLAW_TAGS.items():
        assert isinstance(tag, str) and isinstance(desc, str) and desc


def test_unknown_tag_reports_code_flaw(captured_logger):
    logger, handler = captured_logger
    AppFlaw.report(
        invariant_id="something",
        tags=["bogus_tag"],
        handling=HANDLING_ABORT_OPERATION,
        message="m",
        logger=logger,
    )
    flaws = _flaw_records(handler)
    # Two emissions: the misuse `code` Flaw, plus the original.
    misuse = [r for r in flaws if r.message_data["invariant_id"] == "flaw_api_misuse"]
    assert len(misuse) == 1
    assert misuse[0].message_data["flaw_class"] == "code"
    assert any(r.message_data["invariant_id"] == "something" for r in flaws)


def test_empty_tags_reports_code_flaw(captured_logger):
    logger, handler = captured_logger
    CodeFlaw.report(invariant_id="x", tags=[], handling=HANDLING_ABORT_OPERATION, message="m", logger=logger)
    assert any(r.message_data["invariant_id"] == "flaw_api_misuse" for r in _flaw_records(handler))


def test_unknown_handling_reports_code_flaw(captured_logger):
    logger, handler = captured_logger
    CodeFlaw.report(invariant_id="x", tags=["security"], handling="bogus", message="m", logger=logger)
    assert any(r.message_data["invariant_id"] == "flaw_api_misuse" for r in _flaw_records(handler))


# ---------------------------------------------------------------------------
# Wired instance: plugin mount collision is an `app` Flaw (req-flaw-first-instances)
# ---------------------------------------------------------------------------


class _FakePluginConfig:
    def __init__(self, label: str, router: object | None):
        self.label = label
        self.verbose_name = None
        self._router = router

    def get_api_router(self) -> object | None:
        return self._router


def test_plugin_collision_emits_app_flaw_and_refuses():
    from tap_api import api as api_module

    handler = _Capture()
    api_module.logger.addHandler(handler)
    api_module.logger.setLevel(logging.DEBUG)
    try:
        with pytest.raises(ImproperlyConfigured):
            api_module.resolve_plugin_mounts([_FakePluginConfig("dup", object()), _FakePluginConfig("dup", object())])
    finally:
        api_module.logger.removeHandler(handler)

    flaws = _flaw_records(handler)
    assert any(
        r.message_data["flaw_class"] == "app"
        and r.message_data["invariant_id"] == "plugin_mount_collision"
        and r.message_data["flaw_tags"] == ["integration"]
        for r in flaws
    )


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
