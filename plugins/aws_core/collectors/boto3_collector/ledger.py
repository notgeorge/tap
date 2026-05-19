"""Per-run AWS call audit ledger.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-audit-ledger) — step one of the audit-verifiability
theme.

Captures, at the boto3 boundary, every AWS call's request id + outcome +
AWS-side timestamp so a run can later be correlated to the account's own
CloudTrail (`requestID` ↔ recorded request id; `eventTime` ↔ the response
`Date`). It is run provenance: the collector drains it into
``CollectionJob.results`` once per run, **never** onto a resource node —
per-call request ids change every run and are exactly why
``ResponseMetadata`` is stripped from node payloads
(``req-aws-collector-field-projection-6``).

Capture uses botocore's session event emitter, so every enumerate call,
paginator page, fan-out sub-call, and the STS identity probe is recorded
with no per-resource code and no engine-signature change:

- ``before-call`` stashes ``{service, operation}`` on the call ``context``
  (the only correlation handle the error path gets). It returns ``None`` —
  ``before-call`` is ``emit_until_response``; a non-None return would
  short-circuit the real AWS call.
- ``after-call`` fires for every call that got an HTTP response, including
  4xx/5xx that botocore turns into ``ClientError`` (the response is parsed,
  with ``ResponseMetadata`` + ``Error.Code``, *before* the raise). This is
  where ``denied`` / ``throttled`` are observed.
- ``after-call-error`` fires only when the transport itself raised (no HTTP
  response — connect/read timeout, endpoint failure): an ``error`` entry
  from the stashed context.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

_DENIED = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedOperation",
        "AuthFailure",
        "Forbidden",
        "403",
        "401",
    }
)
_THROTTLED = frozenset(
    {
        "Throttling",
        "ThrottlingException",
        "ThrottledException",
        "RequestThrottled",
        "RequestThrottledException",
        "RequestLimitExceeded",
        "TooManyRequestsException",
        "SlowDown",
        "429",
    }
)
_OUTCOME_ORDER = ("ok", "absent", "denied", "throttled", "error")


def _is_absent_code(code: str) -> bool:
    """AWS's "not configured" signal — shares the hydrate dialect.

    Mirrors :func:`hydrate._classify`'s absent rule (``NoSuch*`` /
    ``*NotFound*``) by convention so the system speaks one vocabulary; a
    future cleanup may factor a single shared classifier (not now).
    """
    return code.startswith("NoSuch") or code.endswith(
        ("NotFound", "NotFoundError")
    )


def _classify(http_status: int | None, error_code: str | None) -> str:
    """Call outcome ∈ ok | absent | denied | throttled | error.

    Aligned with the hydrate classifier vocabulary, including ``absent``:
    AWS's expected "not configured" 404 (e.g. ``NoSuchBucketPolicy``) is a
    first-class outcome, never folded into ``error`` — conflating them is
    the anti-pattern ``req-aws-collector-hydrate-6`` forbids.
    """
    if error_code:
        if error_code in _DENIED:
            return "denied"
        if error_code in _THROTTLED:
            return "throttled"
        if _is_absent_code(error_code):
            return "absent"
    if http_status is not None:
        if 200 <= http_status < 300:
            return "ok"
        if http_status in (401, 403):
            return "denied"
        if http_status == 429:
            return "throttled"
        return "error"
    return "error"


class CallLedger:
    """Accumulates one entry per AWS call for the duration of a run."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    # -- botocore wiring -------------------------------------------------
    def attach(self, boto3_session: Any) -> None:
        """Register the handlers on a boto3 session (before any client)."""
        events = boto3_session.events
        events.register("before-call", self._before_call)
        events.register("after-call", self._after_call)
        events.register("after-call-error", self._after_call_error)

    @staticmethod
    def _service_op(model: Any) -> tuple[str, str]:
        service_model = getattr(model, "service_model", None)
        service = getattr(service_model, "service_name", "") if service_model else ""
        return service, getattr(model, "name", "")

    def _before_call(
        self, model: Any = None, context: Any = None, **_kwargs: Any
    ) -> None:
        if context is not None and model is not None:
            service, operation = self._service_op(model)
            context["_tap_audit"] = {"service": service, "operation": operation}
        return None  # emit_until_response: must not short-circuit the call

    def _after_call(
        self,
        parsed: Any = None,
        model: Any = None,
        **_kwargs: Any,
    ) -> None:
        parsed = parsed or {}
        meta = parsed.get("ResponseMetadata") or {}
        headers = meta.get("HTTPHeaders") or {}
        status = meta.get("HTTPStatusCode")
        error_code = (parsed.get("Error") or {}).get("Code")
        service, operation = (
            self._service_op(model) if model is not None else ("", "")
        )
        self._entries.append(
            {
                "service": service,
                "operation": operation,
                "request_id": meta.get("RequestId")
                or headers.get("x-amz-request-id"),
                "host_id": meta.get("HostId") or headers.get("x-amz-id-2"),
                "http_status": status,
                "outcome": _classify(status, error_code),
                "response_date": headers.get("date"),
            }
        )

    def _after_call_error(
        self, exception: Any = None, context: Any = None, **_kwargs: Any
    ) -> None:
        audit = (context or {}).get("_tap_audit", {})
        response = getattr(exception, "response", None)
        meta: dict[str, Any] = {}
        error_code = None
        if isinstance(response, dict):
            meta = response.get("ResponseMetadata") or {}
            error_code = (response.get("Error") or {}).get("Code")
        headers = meta.get("HTTPHeaders") or {}
        status = meta.get("HTTPStatusCode")
        self._entries.append(
            {
                "service": audit.get("service", ""),
                "operation": audit.get("operation", ""),
                "request_id": meta.get("RequestId")
                or headers.get("x-amz-request-id"),
                "host_id": meta.get("HostId"),
                "http_status": status,
                "outcome": _classify(status, error_code)
                if (status is not None or error_code)
                else "error",
                "response_date": headers.get("date"),
            }
        )

    # -- drain -----------------------------------------------------------
    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def summary(self) -> str:
        counts = Counter(e["outcome"] for e in self._entries)
        parts = ", ".join(
            f"{counts[k]} {k}" for k in _OUTCOME_ORDER if counts.get(k)
        )
        total = f"{len(self._entries)} AWS call(s)"
        return f"{total}: {parts}" if parts else total
