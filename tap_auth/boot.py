"""Auth boot section — config-time readers + boot-phase application (req-tap-auth-boot).

Two responsibilities, deliberately split by when they run:

  * **Settings-time readers** (``providers_for_settings`` / ``initial_admins_for_settings``
    / ``local_password_enabled_from_profile``) read the boot profile's ``auth``
    section from disk with NO Django model imports, so ``tap/settings.py`` can
    populate ``TAP_AUTH_PROVIDERS`` etc. at import time. One declarative source
    (the profile) feeds both the running server's settings and the boot command.

  * **Boot-phase application** (``apply_auth_boot_section``) runs inside the boot
    ``auth`` phase (after capabilities/groups/actors/initial-admin sync): it
    validates the section against tap_auth's schema fragment, runs each provider's
    self-tests (live for a deploy boot — req-tap-auth-providers-6), enforces the
    Django deploy posture, and enforces the last-admin invariant (boot must not
    converge to zero active human tap_admin unless break-glass is declared).

Secrets are never in the profile — providers reference an auth-scoped secret by
key (req-tap-auth-providers-3).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
from django.conf import settings

logger = logging.getLogger(__name__)

Echo = Callable[[str], None]

_FRAGMENT_PATH = Path(__file__).resolve().parent / "schemas" / "auth-boot-section.schema.json"


class AuthBootError(Exception):
    """Raised when the auth boot section is invalid or its application must abort."""


@lru_cache(maxsize=1)
def _fragment_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(_FRAGMENT_PATH.read_text())
    return schema


# --------------------------------------------------------------------------- #
# settings-time readers (no model imports)
# --------------------------------------------------------------------------- #


def _profile_path(profile_id: str) -> Path:
    # Computed from BASE_DIR rather than importing tap_boot, so this module is a
    # clean settings-time dependency and tap_auth does not depend on tap_boot.
    return Path(settings.BASE_DIR) / "boot" / f"{profile_id}.json"


def read_auth_section(profile_id: str) -> dict[str, Any]:
    """Return the raw ``auth`` section of ``boot/<profile_id>.json`` ({} if absent).

    Tolerant by design — a malformed profile is the boot command's problem to
    surface loudly; settings-time reading must not crash the process on a bad
    file. Returns {} on any read/parse problem (logged).
    """
    if not profile_id:
        return {}
    path = _profile_path(profile_id)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[2f1e] could not read auth section from %s: %s", path, exc)
        return {}
    section = data.get("auth")
    return section if isinstance(section, dict) else {}


def providers_for_settings(profile_id: str) -> list[dict[str, Any]]:
    """Provider config dicts for ``TAP_AUTH_PROVIDERS`` from the profile's auth section."""
    providers = read_auth_section(profile_id).get("providers")
    return providers if isinstance(providers, list) else []


def initial_admins_for_settings(profile_id: str) -> list[str]:
    """Initial-admin emails for ``TAP_AUTH_INITIAL_ADMINS`` from the profile."""
    admins = read_auth_section(profile_id).get("initial_admins")
    return admins if isinstance(admins, list) else []


def local_password_enabled_from_profile(profile_id: str) -> bool:
    """Whether local password auth is enabled (default True when unset)."""
    return bool(read_auth_section(profile_id).get("local_password_enabled", True))


# --------------------------------------------------------------------------- #
# boot-phase application
# --------------------------------------------------------------------------- #


def validate_auth_section(section: dict[str, Any]) -> None:
    """Validate an auth section against the tap_auth schema fragment. Raises
    AuthBootError on any violation (malformed config fails boot loudly)."""
    try:
        jsonschema.validate(instance=section, schema=_fragment_schema())
    except jsonschema.ValidationError as exc:
        loc = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise AuthBootError(f"auth section failed schema validation at {loc}: {exc.message}") from exc


def apply_auth_boot_section(section: dict[str, Any], *, deploy: bool, echo: Echo) -> None:
    """Validate and apply the auth boot section (req-tap-auth-boot).

    ``deploy`` (True when not DEBUG) selects the strict posture: live provider
    self-tests + the Django deploy-security gate are enforced and FAIL aborts
    boot; a dev boot relaxes both but logs loudly. Always enforces the
    last-admin invariant.
    """
    from tap_auth.providers import ProviderConfig, get_provider

    validate_auth_section(section)

    if deploy:
        _check_deploy_posture(echo)

    providers = section.get("providers") or []
    for raw in providers:
        config = ProviderConfig.from_dict(raw)
        provider = get_provider(config.type)  # unknown type → UnknownProviderType (fails boot)
        try:
            secrets = provider.resolve_secrets(config)
        except Exception as exc:  # noqa: BLE001 - resolution failure is a boot-fatal config error
            if config.critical_for_boot:
                raise AuthBootError(f"provider '{config.id}': secret resolution failed: {exc}") from exc
            logger.warning("[7c4a] non-critical provider %s: secret resolution failed: %s", config.id, exc)
            secrets = {}
        results = provider.self_test(config, secrets, live=deploy)
        fails = [r for r in results if not r.ok]
        for r in results:
            echo(f"  [auth] provider {config.id}: {r.status.value.upper():4} {r.phase.value:<7} {r.check}: {r.message}")
        if fails and config.critical_for_boot:
            raise AuthBootError(
                f"provider '{config.id}' self-test FAILED: {[r.check for r in fails]}; "
                "critical_for_boot — aborting boot."
            )
        if fails:
            logger.warning("[3b6d] non-critical provider %s self-test FAILED: %s", config.id, [r.check for r in fails])

    _enforce_last_admin_invariant(
        allow_lockout=bool(section.get("allow_admin_lockout", False)),
        declared_admin_path=bool(section.get("initial_admins")),
        echo=echo,
    )
    echo("Auth phase: auth section applied (providers validated, last-admin invariant enforced).")


def _check_deploy_posture(echo: Echo) -> None:
    """Enforce the Django deployment-security posture before serving an
    auth-enabled deploy boot (req-tap-auth-boot). FAIL aborts."""
    problems: list[str] = []
    if not settings.SECRET_KEY or settings.SECRET_KEY == "dev-secret-key-change-me":
        problems.append("SECRET_KEY is unset or the dev default")
    if settings.DEBUG:
        problems.append("DEBUG is True")
    hosts = [h for h in (settings.ALLOWED_HOSTS or []) if h]
    if not hosts or "*" in hosts:
        problems.append("ALLOWED_HOSTS is empty or a wildcard")
    if not getattr(settings, "SESSION_COOKIE_SECURE", False):
        problems.append("SESSION_COOKIE_SECURE is False")
    if not getattr(settings, "CSRF_COOKIE_SECURE", False):
        problems.append("CSRF_COOKIE_SECURE is False")
    if problems:
        raise AuthBootError("deploy security posture check failed: " + "; ".join(problems))
    echo("Auth phase: deploy security posture OK.")


def _enforce_last_admin_invariant(*, allow_lockout: bool, declared_admin_path: bool, echo: Echo) -> None:
    """Boot must not converge to zero active human tap_admin (req-tap-auth-boot).

    Satisfied when ANY of: an active human admin already exists; the profile
    declares ``initial_admins`` (a path to admin on first login — not a lockout);
    or ``allow_admin_lockout`` break-glass is set. Otherwise a hard boot failure
    (recovery via the out-of-band management/shell floor).
    """
    from django.contrib.auth import get_user_model

    from tap_auth.models import UserKind

    user_model = get_user_model()
    active_human_admins = user_model.objects.filter(
        is_active=True,
        deactivated_at__isnull=True,
        user_kind=UserKind.HUMAN,
        groups__name="tap_admin",
    ).count()

    if active_human_admins > 0:
        echo(f"Auth phase: last-admin invariant OK ({active_human_admins} active human admin(s)).")
        return
    if declared_admin_path:
        echo("Auth phase: last-admin invariant OK (initial_admins declared — admin on first login).")
        return
    if allow_lockout:
        logger.warning("[5e22] admin lockout permitted by break-glass: zero active human tap_admin")
        echo("Auth phase: WARNING — zero active human admin, permitted by allow_admin_lockout.")
        return
    raise AuthBootError(
        "applying this profile would leave NO active human tap_admin, and neither initial_admins "
        "nor allow_admin_lockout is set. Declare an initial admin (auth.initial_admins + a login) "
        "or set allow_admin_lockout for a deliberate headless standup. Aborting."
    )
