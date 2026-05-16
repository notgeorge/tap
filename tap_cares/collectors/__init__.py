"""tap_cares collector runtime primitives."""

from tap_cares.collectors.base import CollectorBase
from tap_cares.collectors.config import CollectorConfig
from tap_cares.collectors.readiness import (
    CollectorDocRef,
    CollectorReadinessStatus,
    CollectorSelfTestCheck,
    CollectorSelfTestCheckStatus,
    CollectorSelfTestResult,
    check_fail,
    check_pass,
    check_skip,
    check_warn,
)

__all__ = [
    "CollectorBase",
    "CollectorConfig",
    "CollectorDocRef",
    "CollectorReadinessStatus",
    "CollectorSelfTestCheck",
    "CollectorSelfTestCheckStatus",
    "CollectorSelfTestResult",
    "check_fail",
    "check_pass",
    "check_skip",
    "check_warn",
]
