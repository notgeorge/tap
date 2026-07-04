"""Reserved cross-cutting signals — the shared model behind ABORT and CONCERN.

`req-tap-logging-reserved-signals` (spec-tap-logging.md).

A **reserved signal** is the exception to per-producer `message_code` convention:
a cross-cutting, machine-selectable event with a reserved `UPPER_SNAKE`
`message_code`, a fixed `message_data` payload, a severity, a minting helper, and
a greppable console sentinel. Filtering `message_code == "<CODE>"` selects every
occurrence across every producer; the payload fields route it.

TAP has three reserved signals:

- **`FLAW`** — a should-never-happen invariant violation (`spec-tap-flaw-v0.md`,
  `tap/flaws.py`). Richer than the other two (blame class + handling), it keeps
  its own module and spec and is *registered* as a member, not hosted here.
- **`ABORT`** — a fatal, "stop waiting" lifecycle stop. Hosted here.
- **`CONCERN`** — permitted-but-suspicious behavior TAP can't (yet) prevent; the
  detective signal for the plugin-safety discipline
  (`spec-security-posture.md`, `req-sec-concern-gaps`). Hosted here.

`ABORT` and `CONCERN` are lightweight, so they live together here and share one
emit primitive (:func:`emit_signal`) — one place that renders the greppable
sentinel line and attaches the structured `{message_code, message_data}` via
``extra=`` so the record is already structured for a future JSON handler. The
helpers are re-exported from ``tap.logging`` for backwards compatibility, so
``from tap.logging import abort`` keeps working.

This module is stdlib + `tap.logging_domain_tags` only (no dependency on the
logging-config builder), so it imports cleanly wherever a signal is emitted.
"""

from __future__ import annotations

import logging
from typing import Any

from tap.logging_domain_tags import domain_tag_problems

# --------------------------------------------------------------------------- #
# Console sentinels — the stable tokens watchers / SIEM / on-call grep for.
# The helpers' console rendering MUST keep these exact prefixes; shell watchers
# (scripts/spawn-session.sh, scripts/gate-lean for ABORT) tail for them.
# --------------------------------------------------------------------------- #
ABORT_SENTINEL = "TAP-ABORT"
CONCERN_SENTINEL = "TAP-CONCERN"

ABORT_MESSAGE_CODE = "ABORT"
CONCERN_MESSAGE_CODE = "CONCERN"


def emit_signal(
    logger: logging.Logger,
    *,
    level: int,
    sentinel: str,
    message_code: str,
    domain: str,
    reason: str,
    message_data: dict[str, Any],
    exc_info: bool = False,
    stacklevel: int = 3,
) -> None:
    """Emit one reserved-signal record — the shared path for ABORT and CONCERN.

    Renders the stable, greppable ``<sentinel>: <domain>: <reason>`` console line
    and attaches the structured ``{message_code, message_data}`` via ``extra=`` so
    the same record is ready for a future JSON handler (matching how `FLAW` emits).
    One site token (`[0eec]`) covers every signal emission — like `FLAW`'s single
    emit token — since the emission callsite is here; the ``sentinel`` and
    ``domain`` name the true source for diagnosis.

    Args:
        logger: the emitting component's module logger.
        level: the record level (ERROR/CRITICAL for ABORT, WARNING for CONCERN).
        sentinel: the console token (`ABORT_SENTINEL` / `CONCERN_SENTINEL`).
        message_code: the reserved `UPPER_SNAKE` code for the structured payload.
        domain: the failing/detecting subsystem.
        reason: short, secret-free, machine-and-human legible cause.
        message_data: the full structured payload for the reserved code.
        exc_info: pass ``True`` inside an ``except`` to attach the traceback.
        stacklevel: frames from this ``logger.log`` up to the true source; default
            3 attributes the record to the caller of the signal helper (caller →
            helper → here), not to this primitive.
    """
    logger.log(
        level,
        "[0eec] %s: %s: %s",
        sentinel,
        domain,
        reason,
        exc_info=exc_info,
        stacklevel=stacklevel,
        extra={"message_code": message_code, "message_data": message_data},
    )


def abort(logger: logging.Logger, domain: str, reason: str, *, exc_info: bool = False) -> None:
    """Emit the reserved ABORT signal (``req-tap-logging-abort-signal``).

    A fatal, unrecoverable "give up" event that a watcher should act on. Emits
    exactly one record and does **not** itself exit — the caller raises/exits, so
    control flow stays explicit at the call site.

    Args:
        logger: the caller's module logger, so the record is attributed to the
            failing component.
        domain: the failing subsystem/stage — ``preboot`` / ``migrate`` / ``boot`` /
            ``health`` / ``collector`` / … (extensible as consumers appear).
        reason: short, machine-and-human legible cause. Keep secret-free.
        exc_info: pass ``True`` inside an ``except`` to attach the traceback.

    Rendering (``req-tap-logging-format``): the ``console`` handler renders this as
    the greppable ``TAP-ABORT: <domain>: <reason>`` line every shell watcher tails.
    """
    emit_signal(
        logger,
        level=logging.ERROR,
        sentinel=ABORT_SENTINEL,
        message_code=ABORT_MESSAGE_CODE,
        domain=domain,
        reason=reason,
        message_data={"domain": domain, "reason": reason},
        exc_info=exc_info,
    )


def concern(
    logger: logging.Logger,
    domain: str,
    concern_type: str,
    reason: str,
    *,
    tags: tuple[str, ...] = ("security",),
) -> None:
    """Emit the reserved CONCERN signal (``req-tap-logging-concern-signal``).

    A **permitted-but-suspicious** "somebody's being sus" event — the detective
    tripwire for behavior TAP cannot (yet) *prevent* (notably a plugin overstepping;
    see ``spec-security-posture.md`` ``req-sec-concern-gaps``). Non-fatal: emits one
    ``WARNING`` record and returns; the producer proceeds (a tripwire observes, it
    does not stop). It makes **no** invariant claim — unlike `FLAW` — so it may
    carry false positives; that is acceptable because it blocks nothing.

    Args:
        logger: the detecting component's module logger.
        domain: the subsystem that detected it — ``secrets`` / ``plugins`` / … .
        concern_type: a stable token naming *what kind* of suspicious behavior
            (the routing key, e.g. ``cross_scope_secret_access``).
        reason: short, machine-and-human legible description. MUST be secret-free —
            names/scopes/keys only, never secret material.
        tags: `req-tap-logging-domain-tags` domain tags (default ``("security",)``).
            An unregistered tag falls back to ``("security",)`` so a producer
            mistake still emits the concern rather than raising in the emit path.

    Rendering (``req-tap-logging-format``): the ``console`` handler renders this as
    the greppable ``TAP-CONCERN: <domain>: <reason>`` line a security monitor tails.
    """
    tag_list = list(tags)
    if domain_tag_problems(tag_list):
        tag_list = ["security"]
    emit_signal(
        logger,
        level=logging.WARNING,
        sentinel=CONCERN_SENTINEL,
        message_code=CONCERN_MESSAGE_CODE,
        domain=domain,
        reason=reason,
        message_data={"domain": domain, "concern_type": concern_type, "tags": tag_list, "reason": reason},
    )


__all__ = [
    "ABORT_SENTINEL",
    "CONCERN_SENTINEL",
    "ABORT_MESSAGE_CODE",
    "CONCERN_MESSAGE_CODE",
    "emit_signal",
    "abort",
    "concern",
]
