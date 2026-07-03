"""Tests for the `tap_localtime` template filter (spec-web-time-display).

Covers req-web-time-utc-canonical (UTC normalization is non-destructive at the
render hop), req-web-time-local-display-3 (the no-JS fallback body is labeled
UTC, never an unlabeled local time), req-web-time-zone-disclosure (the exact UTC
instant is recoverable from both the tooltip and the machine `datetime`
attribute), and req-web-time-single-helper (one server entry point for
human-facing times).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from tap_web.panels.viewer_panel import _format_value
from tap_web.templatetags.tap_time import tap_localtime
from tap_web.timefmt import render_local_time

# A fixed UTC instant used across cases: 2026-07-02 14:30:05 UTC.
_UTC = datetime(2026, 7, 2, 14, 30, 5, tzinfo=UTC)


def test_aware_utc_renders_time_element() -> None:
    """An aware UTC datetime renders a <time> carrying the canonical instant."""
    html = str(tap_localtime(_UTC))
    # Machine value: ISO-8601 UTC with a Z suffix (req-web-time-utc-canonical).
    assert 'datetime="2026-07-02T14:30:05Z"' in html
    # Localization is deferred to the browser — the marker attribute is present.
    assert "data-tap-localtime" in html
    # Tooltip discloses the exact UTC instant (req-web-time-zone-disclosure-2).
    assert 'title="2026-07-02 14:30:05 UTC"' in html
    # No-JS fallback body is labeled UTC, minute precision (req-web-time-local-display-3).
    assert ">2026-07-02 14:30 UTC</time>" in html


def test_non_utc_aware_is_normalized_to_utc() -> None:
    """A non-UTC aware datetime is converted to UTC, not rendered in its own zone."""
    # 10:30:05 at UTC-4 is the same instant as 14:30:05 UTC.
    eastern = timezone(timedelta(hours=-4))
    value = datetime(2026, 7, 2, 10, 30, 5, tzinfo=eastern)
    html = str(tap_localtime(value))
    assert 'datetime="2026-07-02T14:30:05Z"' in html
    assert 'title="2026-07-02 14:30:05 UTC"' in html


def test_naive_datetime_is_assumed_utc() -> None:
    """A naive datetime is assumed UTC (TAP stores UTC), not the server zone."""
    naive = datetime(2026, 7, 2, 14, 30, 5)
    html = str(tap_localtime(naive))
    assert 'datetime="2026-07-02T14:30:05Z"' in html


def test_none_renders_em_dash_placeholder() -> None:
    """None renders the em-dash placeholder, matching the prior `default:'—'`."""
    assert str(tap_localtime(None)) == "&mdash;"


def test_non_datetime_passes_through_unchanged() -> None:
    """A non-datetime value is returned unchanged (nothing to localize)."""
    assert tap_localtime("not a datetime") == "not a datetime"


def test_output_is_html_safe_and_marked_current_utc_only() -> None:
    """The rendered element is a single, well-formed <time> tag (one entry point)."""
    html = str(tap_localtime(_UTC))
    assert html.count("<time ") == 1
    assert html.endswith("</time>")


def test_filter_delegates_to_shared_renderer() -> None:
    """The filter and the shared server renderer produce identical output."""
    assert str(tap_localtime(_UTC)) == str(render_local_time(_UTC))


def test_viewer_panel_datetime_localizes() -> None:
    """A datetime entity field renders through the shared <time> helper."""
    text, is_block = _format_value(_UTC)
    assert "data-tap-localtime" in str(text)
    assert 'datetime="2026-07-02T14:30:05Z"' in str(text)
    assert is_block is False


def test_viewer_panel_bare_date_is_not_localized() -> None:
    """A bare date has no zone; it stays a plain ISO date (no day-shift risk)."""
    text, is_block = _format_value(date(2026, 7, 2))
    assert text == "2026-07-02"
    assert "<time" not in str(text)
