"""Template tags for TAP human-facing time rendering (spec-web-time-display).

Usage::

    {% load tap_time %}
    {{ batch.started_at|tap_localtime }}

TAP stores and transmits time as absolute UTC (`req-web-time-utc-canonical`).
The ``tap_localtime`` filter emits the shared ``<time>`` element (see
:mod:`tap_web.timefmt`); ``localtime.js`` localizes it to the viewer's browser
zone at render time (`req-web-time-local-display`, `req-web-time-single-helper`).
"""

from __future__ import annotations

from datetime import datetime

from django import template
from django.utils.safestring import SafeString

from tap_web.timefmt import MISSING, render_local_time

register = template.Library()


@register.filter
def tap_localtime(value: object) -> SafeString | str:
    """Render a UTC datetime as a browser-localizing ``<time>`` element.

    Args:
        value: An aware (or naive-assumed-UTC) ``datetime``. ``None`` renders an
            em-dash placeholder; a non-datetime value is returned unchanged.

    Returns:
        The shared ``<time>`` element for ``localtime.js`` to localize, or the
        em-dash placeholder for ``None``.
    """
    if value is None:
        return MISSING
    if not isinstance(value, datetime):
        # Not a datetime — nothing to localize; let the caller's value through.
        return value  # type: ignore[return-value]
    return render_local_time(value)
