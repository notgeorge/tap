"""tap_cares startup system checks.

req-tap-cares-secrets-resilient-load (spec-tap-cares-secrets.md).

The secrets loader (`tap_cares.secrets.loader.load_secrets`, run in
`TapCaresConfig.ready`) is resilient: a malformed/duplicate secret file is
recorded in `secret_load_report` rather than raised, so one bad file never
crash-loops `django.setup()`. This check is the *strict* surface that reads
that report and turns it into Django system-check messages:

- a file that declared ``required_for_boot: true`` → :class:`Error`
  (``tap_cares.E001``). ``manage.py check`` exits non-zero and ``runserver``
  refuses to serve — i.e. it fails the validation gate / "blows up the build".
- any other load failure → :class:`Warning` (``tap_cares.W001``): visible but
  non-fatal; the instance runs degraded and the ``tap_health`` secrets probe
  reports it.

Registration happens in :meth:`tap_cares.apps.TapCaresConfig.ready` by
importing this module — importing only registers the check; reading the report
happens later when the check runs. No DB access, so it is safe in ``ready``.

The check is untagged, so it runs on ``manage.py check``, ``runserver``, and
``migrate`` — but NOT under a production WSGI/ASGI server, which does not run
system checks. That gap is exactly what the ``tap_health`` secrets probe (run
via ``manage.py health`` / the internal service) covers.
"""

from __future__ import annotations

from typing import Any

from django.core.checks import Error, Warning, register


@register()
def check_secret_load_failures(app_configs: Any, **kwargs: Any) -> list[Any]:
    """Surface recorded secret-load failures as check messages.

    Args:
        app_configs: App configs Django passes to system checks (unused).
        **kwargs: System-check keyword args (unused).

    Returns:
        One :class:`Error` per blocking (``required_for_boot``) failure and one
        :class:`Warning` per degraded failure; empty when all secrets loaded.
    """
    from tap_cares.secrets.registry import secret_load_report

    messages: list[Any] = []
    for failure in secret_load_report.blocking:
        name = failure.qualified or failure.path
        messages.append(
            Error(
                f"Required-for-boot secret failed to load: {name} — {failure.reason}",
                hint=(
                    "This file declared metadata.required_for_boot=true, so a load "
                    "failure blocks standup. Fix the file (or set required_for_boot "
                    "false to downgrade to a degraded-health warning)."
                ),
                id="tap_cares.E001",
            )
        )
    for failure in secret_load_report.degraded:
        name = failure.qualified or failure.path
        messages.append(
            Warning(
                f"Secret failed to load (degraded): {name} — {failure.reason}",
                hint=(
                    "Capabilities needing this secret will fail at run time via "
                    "resolve_secret. Fix the file, or set metadata.required_for_boot=true "
                    "to make this failure block standup instead."
                ),
                id="tap_cares.W001",
            )
        )
    return messages
