"""Server-side WebAuthn challenge store — single-use + TTL (req-tap-auth-passkey-webauthn-9).

py_webauthn mints the challenge (>=16B CSPRNG; library default 64B) and verifies the
value passed to it, but it does NOT store, bind, or expire it — that is entirely
TAP's responsibility. TAP stashes the challenge in the Django session and consumes
it atomically (``pop``) so a challenge minted for one ceremony cannot be redeemed in
another. Binding is by ceremony ``kind`` + the session itself: registration/
enrollment additionally carries the invitation/user it is bound to; authentication
(usernameless) is bound to the session only — the user is unknown until the assertion
verifies, so binding an auth challenge to a specific user up front is impossible and
is not required.
"""

from __future__ import annotations

import time
from typing import Any

from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

CHALLENGE_TTL_SECONDS = 300  # short-lived: a ceremony completes in seconds
_SESSION_PREFIX = "webauthn_challenge_"


def stash(session: Any, kind: str, challenge: bytes, *, bound: dict[str, Any] | None = None) -> None:
    """Store `challenge` for ceremony `kind` in the session with a TTL and optional
    binding metadata (e.g. the invitation public-id for an enrollment)."""
    session[_SESSION_PREFIX + kind] = {
        "challenge": bytes_to_base64url(challenge),
        "expires_at": time.time() + CHALLENGE_TTL_SECONDS,
        "bound": bound or {},
    }
    session.modified = True


def pop(session: Any, kind: str) -> tuple[bytes, dict[str, Any]] | None:
    """Atomically consume the stashed challenge for `kind`.

    Returns ``(challenge_bytes, bound)`` or ``None`` if absent or expired. Single-use
    by construction: the entry is removed on read, so a second pop returns ``None``.
    """
    data = session.pop(_SESSION_PREFIX + kind, None)
    session.modified = True
    if not data:
        return None
    if time.time() > float(data.get("expires_at", 0)):
        return None
    return base64url_to_bytes(data["challenge"]), dict(data.get("bound", {}))
