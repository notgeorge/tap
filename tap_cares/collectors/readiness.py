"""Collector self-test/readiness result types.

Spec: req-tap-cares-collector-self-test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# Bounded-latency *defaults* (req-tap-cares-collector-self-test-12). These are
# the baseline budget; a collector MAY raise its own budget via the
# CollectorBase.SELF_TEST_*_SECONDS class attributes when it depends on an
# external tool with unavoidable cold-start (with documented justification).
# Enforcement lives in each collector's live check (subprocess timeout, HTTP
# timeout), not here — readiness.py owns no I/O.
LIVE_CHECK_TIMEOUT_SECONDS = 5
SELF_TEST_DEADLINE_SECONDS = 15


class CollectorReadinessStatus(StrEnum):
    READY = "ready"
    WARNING = "warning"
    UNCONFIGURED = "unconfigured"
    MISCONFIGURED = "misconfigured"
    ERROR = "error"


class CollectorSelfTestCheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class CollectorDocRef:
    """Stable reference to canonical user-facing documentation."""

    plugin: str
    doc: str
    section: str = ""
    label: str = ""

    @property
    def ref(self) -> str:
        suffix = f"#{self.section}" if self.section else ""
        return f"{self.plugin}/{self.doc}{suffix}"

    def to_dict(self) -> dict[str, str]:
        return {
            "plugin": self.plugin,
            "doc": self.doc,
            "section": self.section,
            "label": self.label,
            "ref": self.ref,
        }


@dataclass(frozen=True, slots=True)
class CollectorSelfTestCheck:
    """One accumulated self-test check."""

    code: str
    status: CollectorSelfTestCheckStatus
    message: str
    readiness_status: CollectorReadinessStatus | None = None
    context: dict[str, Any] = field(default_factory=dict)
    docs: tuple[CollectorDocRef, ...] = ()

    @property
    def is_failure(self) -> bool:
        return self.status == CollectorSelfTestCheckStatus.FAIL

    @property
    def is_warning(self) -> bool:
        return self.status == CollectorSelfTestCheckStatus.WARN

    @property
    def is_skip(self) -> bool:
        return self.status == CollectorSelfTestCheckStatus.SKIP

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection for persistence on `CollectionJob.self_test`.

        Redaction is the collector's responsibility (`context` must never
        carry secret material per req-tap-cares-collector-self-test-13); this
        only restructures, it does not sanitize.
        """
        return {
            "code": self.code,
            "status": self.status.value,
            "message": self.message,
            "readiness_status": (self.readiness_status.value if self.readiness_status is not None else None),
            "context": dict(self.context),
            "docs": [doc.to_dict() for doc in self.docs],
        }


@dataclass(frozen=True, slots=True)
class CollectorSelfTestResult:
    """Top-level readiness result returned by collector self-tests.

    `checked_at` is mandatory (req-tap-cares-collector-self-test, "Contract
    semantics"): it is the UTC instant the result was produced, and the
    stored `CollectionJob.self_test` plus the "it worked at <time>" answer
    depend on it. It is ordered before the defaulted fields because a
    required field after defaulted fields is an invalid dataclass.
    """

    status: CollectorReadinessStatus
    summary: str
    checked_at: datetime
    checks: tuple[CollectorSelfTestCheck, ...] = ()
    collector_registry: str = ""
    docs: tuple[CollectorDocRef, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def runnable(self) -> bool:
        return self.status in {
            CollectorReadinessStatus.READY,
            CollectorReadinessStatus.WARNING,
        }

    @property
    def failed_checks(self) -> tuple[CollectorSelfTestCheck, ...]:
        return tuple(check for check in self.checks if check.is_failure)

    @property
    def warning_checks(self) -> tuple[CollectorSelfTestCheck, ...]:
        """Checks that raised a genuine advisory.

        Skips are deliberately excluded: a `skip` is informational and does
        not escalate readiness (req-tap-cares-collector-self-test-14). Use
        `skipped_checks` to surface "could not test" separately.
        """
        return tuple(check for check in self.checks if check.is_warning)

    @property
    def skipped_checks(self) -> tuple[CollectorSelfTestCheck, ...]:
        return tuple(check for check in self.checks if check.is_skip)

    @classmethod
    def from_checks(
        cls,
        checks: list[CollectorSelfTestCheck] | tuple[CollectorSelfTestCheck, ...],
        *,
        summary: str = "",
        checked_at: datetime | None = None,
        collector_registry: str = "",
        docs: tuple[CollectorDocRef, ...] = (),
        context: dict[str, Any] | None = None,
    ) -> CollectorSelfTestResult:
        checks_tuple = tuple(checks)
        status = _derive_status(checks_tuple)
        return cls(
            status=status,
            summary=summary or _default_summary(status, checks_tuple),
            checked_at=checked_at or datetime.now(UTC),
            checks=checks_tuple,
            collector_registry=collector_registry,
            docs=docs,
            context=context or {},
        )

    def with_collector_registry(self, collector_registry: str) -> CollectorSelfTestResult:
        if self.collector_registry == collector_registry:
            return self
        return CollectorSelfTestResult(
            status=self.status,
            summary=self.summary,
            checked_at=self.checked_at,
            checks=self.checks,
            collector_registry=collector_registry,
            docs=self.docs,
            context=self.context,
        )

    def with_checked_at(self, checked_at: datetime) -> CollectorSelfTestResult:
        """Re-stamp `checked_at`.

        The pure hook stamps the instant it produced the result; the service
        entry point re-stamps so every branch (success, RUNNER_UNAVAILABLE,
        SELF_TEST_EXCEPTION) carries one authoritative instant
        (req-tap-cares-collector-self-test-11, stamping responsibility).
        """
        if self.checked_at == checked_at:
            return self
        return CollectorSelfTestResult(
            status=self.status,
            summary=self.summary,
            checked_at=checked_at,
            checks=self.checks,
            collector_registry=self.collector_registry,
            docs=self.docs,
            context=self.context,
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection persisted to `CollectionJob.self_test`.

        Redaction-safe is the collector's contract
        (req-tap-cares-collector-self-test-13): this restructures into
        JSON primitives but does not sanitize `context`.
        """
        return {
            "status": self.status.value,
            "summary": self.summary,
            "checked_at": self.checked_at.isoformat(),
            "collector_registry": self.collector_registry,
            "runnable": self.runnable,
            "checks": [check.to_dict() for check in self.checks],
            "docs": [doc.to_dict() for doc in self.docs],
            "context": dict(self.context),
        }


def check_pass(
    code: str,
    message: str,
    *,
    context: dict[str, Any] | None = None,
    docs: tuple[CollectorDocRef, ...] = (),
) -> CollectorSelfTestCheck:
    return CollectorSelfTestCheck(
        code=code,
        status=CollectorSelfTestCheckStatus.PASS,
        message=message,
        context=context or {},
        docs=docs,
    )


def check_warn(
    code: str,
    message: str,
    *,
    context: dict[str, Any] | None = None,
    docs: tuple[CollectorDocRef, ...] = (),
) -> CollectorSelfTestCheck:
    return CollectorSelfTestCheck(
        code=code,
        status=CollectorSelfTestCheckStatus.WARN,
        message=message,
        readiness_status=CollectorReadinessStatus.WARNING,
        context=context or {},
        docs=docs,
    )


def check_skip(
    code: str,
    message: str,
    *,
    context: dict[str, Any] | None = None,
    docs: tuple[CollectorDocRef, ...] = (),
) -> CollectorSelfTestCheck:
    # A skip is informational and must NOT escalate readiness
    # (req-tap-cares-collector-self-test-14). readiness_status stays None so
    # _derive_status does not treat a skip-only result as `warning`.
    return CollectorSelfTestCheck(
        code=code,
        status=CollectorSelfTestCheckStatus.SKIP,
        message=message,
        context=context or {},
        docs=docs,
    )


def check_fail(
    code: str,
    message: str,
    *,
    readiness_status: CollectorReadinessStatus,
    context: dict[str, Any] | None = None,
    docs: tuple[CollectorDocRef, ...] = (),
) -> CollectorSelfTestCheck:
    if readiness_status in {
        CollectorReadinessStatus.READY,
        CollectorReadinessStatus.WARNING,
    }:
        raise ValueError("Failed self-test checks must use a non-runnable readiness status.")
    return CollectorSelfTestCheck(
        code=code,
        status=CollectorSelfTestCheckStatus.FAIL,
        message=message,
        readiness_status=readiness_status,
        context=context or {},
        docs=docs,
    )


def _derive_status(
    checks: tuple[CollectorSelfTestCheck, ...],
) -> CollectorReadinessStatus:
    failures = [check for check in checks if check.is_failure]
    if failures:
        for candidate in (
            CollectorReadinessStatus.UNCONFIGURED,
            CollectorReadinessStatus.MISCONFIGURED,
            CollectorReadinessStatus.ERROR,
        ):
            if any(check.readiness_status == candidate for check in failures):
                return candidate
        return CollectorReadinessStatus.ERROR
    # Skip does not escalate: status derives only from fail / warn
    # (req-tap-cares-collector-self-test-14). A skip-only result is `ready`.
    if any(check.is_warning for check in checks):
        return CollectorReadinessStatus.WARNING
    return CollectorReadinessStatus.READY


def _default_summary(
    status: CollectorReadinessStatus,
    checks: tuple[CollectorSelfTestCheck, ...],
) -> str:
    if status == CollectorReadinessStatus.READY:
        return "Collector self-test passed."
    if status == CollectorReadinessStatus.WARNING:
        return "Collector self-test passed with warnings."
    failures = [check for check in checks if check.is_failure]
    if failures:
        return failures[0].message
    return "Collector self-test did not pass."
