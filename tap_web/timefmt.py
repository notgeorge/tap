"""Server-side human-facing time rendering (spec-web-time-display).

The single source of truth for the *server* side of `req-web-time-single-helper`:
turn a UTC datetime into the ``<time>`` element that ``localtime.js`` localizes
to the viewer's browser zone. Both the ``tap_localtime`` template filter and
server-rendered panel value formatting call :func:`render_local_time`, so every
server-emitted human-facing time is byte-identical and cannot drift apart.

TAP stores and transmits time as absolute UTC (`req-web-time-utc-canonical`);
this module only shapes the presentation element and never mutates the instant.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

# Placeholder for an absent time — matches the prior template `default:"—"`.
MISSING: SafeString = mark_safe("&mdash;")


def render_local_time(value: datetime) -> SafeString:
    """Render a datetime as a browser-localizing ``<time>`` element.

    The element carries the canonical UTC instant in its ``datetime`` attribute
    and ``title`` tooltip (`req-web-time-zone-disclosure`); ``localtime.js``
    rewrites the body to the viewer's local zone with zone disclosure. The
    server-rendered body is labeled UTC so the no-JS fallback is never an
    unlabeled, ambiguous local time (`req-web-time-local-display-3`).

    Args:
        value: An aware datetime (converted to UTC) or a naive datetime (assumed
            UTC — TAP stores UTC, so a naive value is not reinterpreted in the
            server's local zone).

    Returns:
        A safe ``<time>`` element.
    """
    if timezone.is_naive(value):
        value = value.replace(tzinfo=UTC)
    utc = value.astimezone(UTC)
    return format_html(
        '<time datetime="{}" data-tap-localtime title="{}">{}</time>',
        utc.strftime("%Y-%m-%dT%H:%M:%SZ"),  # canonical machine value
        utc.strftime("%Y-%m-%d %H:%M:%S UTC"),  # exact instant, always recoverable
        utc.strftime("%Y-%m-%d %H:%M UTC"),  # no-JS fallback, labeled
    )
