"""Tests for collector self-test/readiness primitives."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tap_cares.collectors import CollectorBase, CollectorConfig
from tap_cares.collectors.readiness import (
    CollectorReadinessStatus,
    CollectorSelfTestResult,
    check_fail,
    check_pass,
    check_skip,
    check_warn,
)
from tap_cares.models import Collector
from tap_cares.services import self_test_collector


class BasicCollector(CollectorBase):
    def run(self) -> None:
        return None


def test_default_self_test_is_ready():
    result = BasicCollector.self_test()

    assert result.status.value == "ready"
    assert result.runnable is True
    assert result.checks[0].code == "RUNNER_REGISTERED"


# ---------------------------------------------------------------------------
# checked_at is mandatory and self-stamping — req-tap-cares-collector-self-test
# ---------------------------------------------------------------------------


def test_from_checks_stamps_checked_at():
    before = datetime.now(UTC)
    result = CollectorSelfTestResult.from_checks([check_pass("OK", "fine")])
    after = datetime.now(UTC)

    assert isinstance(result.checked_at, datetime)
    assert before <= result.checked_at <= after


def test_with_checked_at_re_stamps():
    result = CollectorSelfTestResult.from_checks([check_pass("OK", "fine")])
    stamp = datetime(2026, 1, 1, tzinfo=UTC)

    restamped = result.with_checked_at(stamp)

    assert restamped.checked_at == stamp
    assert result.checked_at != stamp  # original is frozen / unchanged


# ---------------------------------------------------------------------------
# Skip does not escalate — req-tap-cares-collector-self-test-14
# ---------------------------------------------------------------------------


def test_skip_only_result_is_ready():
    result = CollectorSelfTestResult.from_checks([check_pass("A", "ok"), check_skip("B", "could not test B")])

    assert result.status is CollectorReadinessStatus.READY
    assert result.runnable is True


def test_check_skip_has_no_readiness_status():
    skip = check_skip("B", "could not test B")

    assert skip.readiness_status is None
    assert skip.is_skip is True


def test_warn_still_escalates_to_warning():
    result = CollectorSelfTestResult.from_checks(
        [check_pass("A", "ok"), check_warn("W", "heads up"), check_skip("S", "n/a")]
    )

    assert result.status is CollectorReadinessStatus.WARNING
    assert result.warning_checks and result.warning_checks[0].code == "W"
    assert result.skipped_checks and result.skipped_checks[0].code == "S"


# ---------------------------------------------------------------------------
# to_dict() projection persisted to CollectionJob.self_test
# ---------------------------------------------------------------------------


def test_to_dict_is_json_safe_and_complete():
    result = CollectorSelfTestResult.from_checks(
        [
            check_fail(
                "BAD",
                "broken",
                readiness_status=CollectorReadinessStatus.ERROR,
                context={"detail": "redaction-safe text"},
            )
        ],
        collector_registry="scope:key",
    )

    payload = result.to_dict()

    assert payload["status"] == "error"
    assert payload["runnable"] is False
    assert payload["collector_registry"] == "scope:key"
    assert isinstance(payload["checked_at"], str)
    assert payload["checks"][0]["code"] == "BAD"
    assert payload["checks"][0]["readiness_status"] == "error"
    assert payload["checks"][0]["context"] == {"detail": "redaction-safe text"}

    import json

    json.dumps(payload)  # must not raise


@pytest.mark.django_db
def test_service_self_test_reports_missing_runner():
    collector = Collector.objects.create(
        name="Missing runner",
        description="Collector node with no registered runner.",
        collector_registry="missing.scope:nope",
    )

    result = self_test_collector(collector)

    assert result.status.value == "error"
    assert result.runnable is False
    assert result.collector_registry == "missing.scope:nope"
    assert result.checks[0].code == "RUNNER_UNAVAILABLE"


def test_collector_config_import_kept_for_abstract_contract():
    cfg = CollectorConfig(
        collector_entity_id=uuid4(),
        collection_job_entity_id=uuid4(),
    )

    assert cfg.collector_entity_id != cfg.collection_job_entity_id
