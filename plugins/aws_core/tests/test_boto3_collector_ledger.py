"""Unit tests for the per-run AWS call audit ledger (boto3-free, no DB).

Covers req-aws-collector-audit-ledger: outcome classification, the
botocore after-call / after-call-error capture contract, the
before-call context stash, and the single-entry drain shape.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.aws_core.collectors.boto3_collector.ledger import (
    CallLedger,
    _classify,
)


def _model(service: str, operation: str) -> SimpleNamespace:
    # Mirrors botocore OperationModel: .name + .service_model.service_name.
    return SimpleNamespace(
        name=operation, service_model=SimpleNamespace(service_name=service)
    )


def _parsed(status, *, request_id=None, host_id=None, date=None, error_code=None):
    meta = {"HTTPStatusCode": status, "HTTPHeaders": {}}
    if request_id:
        meta["RequestId"] = request_id
    if host_id:
        meta["HostId"] = host_id
    if date:
        meta["HTTPHeaders"]["date"] = date
    parsed = {"ResponseMetadata": meta}
    if error_code:
        parsed["Error"] = {"Code": error_code}
    return parsed


class TestClassify:
    @pytest.mark.parametrize(
        "status,code,expected",
        [
            (200, None, "ok"),
            (204, None, "ok"),
            (403, "AccessDenied", "denied"),
            (400, "AccessDeniedException", "denied"),
            (401, None, "denied"),
            (429, "Throttling", "throttled"),
            (400, "RequestLimitExceeded", "throttled"),
            # AWS "not configured" 404s are absent, never error.
            (404, "NoSuchBucketPolicy", "absent"),
            (404, "ServerSideEncryptionConfigurationNotFoundError", "absent"),
            (404, "NoSuchPublicAccessBlockConfiguration", "absent"),
            (500, "InternalError", "error"),
            (None, None, "error"),
        ],
    )
    def test_classify(self, status, code, expected):
        assert _classify(status, code) == expected


class TestAfterCall:
    def test_ok_entry_full_fields(self):
        led = CallLedger()
        led._after_call(
            parsed=_parsed(
                200,
                request_id="req-1",
                date="Mon, 19 May 2026 07:00:00 GMT",
            ),
            model=_model("lambda", "ListFunctions"),
        )
        (e,) = led.entries
        assert e == {
            "service": "lambda",
            "operation": "ListFunctions",
            "request_id": "req-1",
            "host_id": None,
            "http_status": 200,
            "outcome": "ok",
            "response_date": "Mon, 19 May 2026 07:00:00 GMT",
        }

    def test_after_call_sees_error_response(self):
        # 4xx/5xx are emitted on after-call (before botocore raises).
        led = CallLedger()
        led._after_call(
            parsed=_parsed(403, request_id="r", error_code="AccessDenied"),
            model=_model("s3", "GetBucketPolicy"),
        )
        assert led.entries[0]["outcome"] == "denied"

    def test_s3_not_configured_is_absent_not_error(self):
        led = CallLedger()
        led._after_call(
            parsed=_parsed(404, request_id="r", error_code="NoSuchBucketPolicy"),
            model=_model("s3", "GetBucketPolicyStatus"),
        )
        assert led.entries[0]["outcome"] == "absent"

    def test_s3_host_id_captured(self):
        led = CallLedger()
        led._after_call(
            parsed=_parsed(200, request_id="r", host_id="x-amz-id-2-blob"),
            model=_model("s3", "ListBuckets"),
        )
        assert led.entries[0]["host_id"] == "x-amz-id-2-blob"


class TestAfterCallError:
    def test_transport_error_uses_before_call_context(self):
        led = CallLedger()
        ctx: dict = {}
        led._before_call(model=_model("sts", "GetCallerIdentity"), context=ctx)
        assert ctx["_tap_audit"] == {"service": "sts", "operation": "GetCallerIdentity"}
        led._after_call_error(exception=RuntimeError("conn timeout"), context=ctx)
        e = led.entries[0]
        assert (e["service"], e["operation"], e["outcome"]) == (
            "sts",
            "GetCallerIdentity",
            "error",
        )

    def test_before_call_returns_none(self):
        # before-call is emit_until_response; a truthy return would
        # short-circuit the real AWS call.
        assert CallLedger()._before_call(model=_model("s3", "X"), context={}) is None


class TestDrainShape:
    def test_summary_and_entries_copy(self):
        led = CallLedger()
        led._after_call(parsed=_parsed(200, request_id="a"), model=_model("s3", "ListBuckets"))
        led._after_call(parsed=_parsed(404, error_code="NoSuchBucketPolicy"), model=_model("s3", "GetBucketPolicy"))
        led._after_call(parsed=_parsed(403, error_code="AccessDenied"), model=_model("s3", "GetBucketAcl"))
        led._after_call(parsed=_parsed(429, error_code="Throttling"), model=_model("ec2", "DescribeInstances"))
        assert led.summary() == "4 AWS call(s): 1 ok, 1 absent, 1 denied, 1 throttled"
        snapshot = led.entries
        snapshot.append({"x": 1})
        assert len(led.entries) == 4  # entries returns a copy

    def test_attach_registers_three_handlers(self):
        registered = []
        session = SimpleNamespace(
            events=SimpleNamespace(register=lambda name, fn: registered.append(name))
        )
        CallLedger().attach(session)
        assert registered == ["before-call", "after-call", "after-call-error"]
