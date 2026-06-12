"""Reserved top-level URL prefixes (req-web-page-slug-sanitize.sec, req-tap-auth-app-4).

Page slugs must not shadow real top-level URL prefixes. Rather than maintain a
second, hand-edited list that silently drifts from ``tap/urls.py``, each TAP app
declares the top-level prefixes it mounts via a ``reserved_url_prefixes`` list on
its ``AppConfig``. This module unions those per-app declarations with the
project-level mounts that no single app owns (Django admin, and the forthcoming
``tap_auth`` ``/auth`` mount).

The result is the set of prefixes a Page slug may not occupy. A test
(``tap_web/tests/test_reserved_prefixes.py``) cross-checks this set against the
actual top-level URLconf, so a newly-mounted top-level route that forgets to
declare itself fails CI instead of relying on reviewer memory.
"""

from __future__ import annotations

from django.apps import apps

# Top-level prefixes mounted in tap/urls.py that are not owned by a TAP app
# config. `/admin` is Django's admin (django.contrib.admin — not a TAP AppConfig
# we control). `/auth` is a forward reservation for the tap_auth app
# (req-tap-auth-app-4); when tap_auth becomes a real app it should declare
# `reserved_url_prefixes = ["/auth"]` on its AppConfig and this entry should be
# removed so the prefix lives with its owner.
_PROJECT_RESERVED_PREFIXES: list[str] = ["/admin", "/auth"]


def normalize_prefix(prefix: str) -> str:
    """Return ``prefix`` as ``/<segment...>`` — leading slash, no trailing slash."""
    p = prefix.strip()
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


def get_reserved_url_prefixes() -> list[str]:
    """Collect reserved top-level URL prefixes from all app configs + project.

    Each ``AppConfig`` may declare ``reserved_url_prefixes: list[str]``. The union
    of those declarations, plus the project-level prefixes that no app owns, is
    the set of prefixes a Page slug may not occupy. Returned sorted and
    de-duplicated.
    """
    collected: set[str] = {normalize_prefix(p) for p in _PROJECT_RESERVED_PREFIXES}
    for config in apps.get_app_configs():
        for prefix in getattr(config, "reserved_url_prefixes", []) or []:
            collected.add(normalize_prefix(prefix))
    return sorted(collected)
