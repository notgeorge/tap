"""Chart Panel — tap_web-owned ECharts-backed chart panel type.

v0 ships intentionally bare: the panel registers, the template renders an
empty mount div, the Apache ECharts JS bundle is loaded as a panel asset.
No chart is drawn; no chart-spec config field is read. The chart-spec
layer lands in a future revision when the first real consumer is scoped.

Spec: tap_web/specs/spec-web-panels-chart.md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


class ChartPanelType:
    """tap_web-owned chart panel type backed by Apache ECharts."""

    slug = "chart"
    label = "Chart"
    view = "tap_web/panels/chart.html"
    css: list[str] = ["tap_web/css/panel-chart.css"]
    js: list[str] = ["tap_web/js/lib/echarts.min.js"]
    editor_view = ""
    config_defaults: dict[str, Any] = {}
    form_class = None

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return {}
