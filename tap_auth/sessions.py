"""Session invalidation — the auditable banhammer (req-tap-auth-sessions).

Three scopes, one boring mechanism (the Django DB session store — no parallel
system, no external cache, consistent with the no-external-cache posture):

  * **global**  — flush every active session (mass logout after a suspected
    platform compromise).
  * **per-user** — invalidate all sessions of one user (get an account out of
    every browser/device now). The DB backend has no user→session FK, so v1 does
    a decode-and-match scan of unexpired sessions (fine at v0 scale).
  * **per-session** — delete one session by key (kill one suspicious session).

Every invalidation is capability-gated (``auth.manage_sessions``), never an
anonymous / ``User=None`` operation, and emits a structured audited security
event (acting actor, scope, redacted target, count). Invalidation is a SEPARATE
lever from disabling login mechanisms and from user deactivation — banning a user
is *composed* from primitives (deactivate + per-user invalidate), never a silent
side effect of either.
"""

from __future__ import annotations

import logging

from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.sessions.models import Session
from django.utils import timezone

from tap_auth.policy import authorize
from tap_grid.caller_context import CallerContext

logger = logging.getLogger(__name__)

CAP_MANAGE_SESSIONS = "auth.manage_sessions"


def _ctx(actor: object) -> CallerContext:
    return CallerContext(user=actor)  # type: ignore[arg-type]


def invalidate_all_sessions(actor: object) -> int:
    """Flush every session in the store. Returns the count invalidated.

    Authorizes ``auth.manage_sessions`` for ``actor`` first (raises on denial).
    """
    authorize(_ctx(actor), CAP_MANAGE_SESSIONS, operation="invalidate_all_sessions")
    count = Session.objects.count()
    Session.objects.all().delete()
    logger.warning(
        "[0fde] sessions invalidated: scope=global actor=%s count=%d",
        _actor_label(actor),
        count,
    )
    return count


def invalidate_user_sessions(actor: object, target_user: object) -> int:
    """Invalidate all active sessions belonging to ``target_user``.

    Decode-and-match scan of unexpired sessions (the DB backend has no
    user→session index). Returns the count invalidated.
    """
    authorize(_ctx(actor), CAP_MANAGE_SESSIONS, operation="invalidate_user_sessions")
    target_id = str(getattr(target_user, "pk", ""))
    to_delete: list[str] = []
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.get_decoded().get(SESSION_KEY) == target_id:
            to_delete.append(session.session_key)
    if to_delete:
        Session.objects.filter(session_key__in=to_delete).delete()
    logger.warning(
        "[34b6] sessions invalidated: scope=user actor=%s target=%s count=%d",
        _actor_label(actor),
        _actor_label(target_user),
        len(to_delete),
    )
    return len(to_delete)


def invalidate_session(actor: object, session_key: str) -> int:
    """Delete one session by key (or redacted handle). Returns 1 if a row was
    removed, 0 if no such session existed."""
    authorize(_ctx(actor), CAP_MANAGE_SESSIONS, operation="invalidate_session")
    deleted, _ = Session.objects.filter(session_key=session_key).delete()
    logger.warning(
        "[7419] sessions invalidated: scope=session actor=%s session=%s count=%d",
        _actor_label(actor),
        _redact_key(session_key),
        deleted,
    )
    return deleted


class AmbiguousUserSelector(Exception):
    """An email selector matched more than one user.

    Email is not a unique identity key (``req-tap-auth-email-not-identity`` /
    ``req-sec-email-not-identity``): duplicate emails are permitted at the DB
    level, so we refuse to silently pick one for a user-targeting operation.
    Resolve by the unique username instead.
    """

    def __init__(self, selector: str, count: int) -> None:
        self.selector = selector
        self.count = count
        super().__init__(
            f"'{selector}' matches {count} users by email; email is not a unique "
            "identifier — resolve by username instead."
        )


def resolve_user(username_or_email: str) -> object | None:
    """Resolve a target user by unique username, else by email.

    The username (``AbstractUser``, ``unique=True``) is an authoritative
    selector. Email is NOT (``req-tap-auth-email-not-identity``): the email
    fallback **fails loud on multiple matches** rather than silently picking the
    first — a mis-resolved ``--as-user`` would run under the wrong authority and a
    mis-resolved ``--user`` would ban the wrong account.

    Raises:
        AmbiguousUserSelector: the email fallback matched more than one user.
    """
    user_model = get_user_model()
    user = user_model.objects.filter(username=username_or_email).first()
    if user is not None:
        return user
    by_email = user_model.objects.filter(email__iexact=username_or_email)
    matches = list(by_email[:2])  # fetch at most 2: enough to detect ambiguity
    if len(matches) > 1:
        raise AmbiguousUserSelector(username_or_email, by_email.count())
    return matches[0] if matches else None


def _actor_label(actor: object) -> str:
    if actor is None:
        return "<none>"
    get_username = getattr(actor, "get_username", None)
    return get_username() if callable(get_username) else str(actor)


def _redact_key(session_key: str) -> str:
    """Session keys are sensitive (they ARE the credential). Log only a short
    prefix handle (req-tap-auth-sessions / logging)."""
    if not session_key:
        return "<none>"
    return f"{session_key[:6]}…"
