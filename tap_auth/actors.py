"""Runtime resolution of built-in program actors (req-tap-auth-builtins).

System-initiated work — boot, collectors, the scheduler, GRIFT import — runs as a
named `program` actor, never `User=None` (req-tap-auth-actor-model). These helpers
resolve the already-synced built-in actors at runtime. The actors themselves are
created by `tap_auth.sync` (run at boot, by the `sync_auth` command, or by the
test fixture); resolving one that does not exist is a hard error, because it means
system-initiated work is running before auth bootstrap — the chicken-and-egg the
boot ordering (req-tap-auth-boot, req-boot-phases) exists to prevent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model

from tap_auth.errors import MissingActor

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

# Built-in keys for the system program actors (mirrors tap_auth.sync).
BOOTLOADER = "tap_bootloader"
SCHEDULER = "tap_scheduler"
COLLECTOR = "tap_collector"


def get_builtin_actor(builtin_key: str) -> AbstractUser:
    """Return the active built-in program actor for `builtin_key`.

    Raises `MissingActor` if it does not exist or is not active — auth sync must
    run before any system-initiated service-layer write. "Active" is the single
    `policy.is_actor_active` definition (is_active AND deactivated_at IS NULL), so
    a built-in carrying a stray `deactivated_at` is treated as absent here exactly
    as `_evaluate` would deny it — never resolved as a usable actor that then fails
    policy (the zombie built-in; doc-auth-per-app-standards "one definition of
    active").
    """
    from tap_auth.policy import is_actor_active

    actor = get_user_model().objects.filter(tap_builtin_key=builtin_key).first()
    if actor is None or not is_actor_active(actor):
        raise MissingActor(
            f"built-in actor {builtin_key!r} not found or inactive — run auth sync "
            "(manage.py sync_auth) before system-initiated work"
        )
    return actor
