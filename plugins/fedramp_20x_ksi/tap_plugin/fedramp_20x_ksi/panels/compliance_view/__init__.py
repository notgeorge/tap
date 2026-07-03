"""FedRAMP 20x KSI Compliance View — plugin-owned panel type.

Displays all KSI indicators in a searchable, filterable table grouped by theme.
Data is loaded via a gryphon query and passed as a raw subgraph envelope to the
browser, where Tabulator renders the grouped table with client-side search and
class filtering.

The default class for the dropdown is resolved server-side from the Grid's
FedRAMP 20x ComplianceContext (regime="fedramp_20x") via gryphon, per
spec-fedramp-20x-ksi-compliance-view.md req-ksi-compview-class-select.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from tap_web.utils import safe_json

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)

_VALID_CLASSES = {"a", "b", "c", "d"}
_FALLBACK_CLASS = "all"

_FEDRAMP_CLASS_QUERY = (
    'MATCH (c:fedramp_20x_ksi__compliance_context) WHERE c.regime = "fedramp_20x" '
    "RETURN c.fedramp_class AS fedramp_class"
)


def _resolve_default_class() -> str:
    """Read the default class from the FedRAMP 20x ComplianceContext.

    Falls back to "all" when no context exists or its fedramp_class is empty.
    """
    from tap_grid.gryphon.executor import execute_gryphon_raw

    try:
        envelope = execute_gryphon_raw(
            _FEDRAMP_CLASS_QUERY, {}, db_alias="search_readonly"
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "[9264] Failed to query FedRAMP 20x ComplianceContext; "
            "defaulting compliance-view class selector to 'all'."
        )
        return _FALLBACK_CLASS

    rows = envelope.get("rows") or envelope.get("nodes") or []
    if not rows:
        logger.warning(
            "[9ed1] No ComplianceContext with regime='fedramp_20x' on this Grid; "
            "defaulting compliance-view class selector to 'all'. Seed one via "
            "the Genericom compliance-context-fedramp grift bundle."
        )
        return _FALLBACK_CLASS

    cls = (rows[0].get("fedramp_class") or "").strip().lower()
    if cls in _VALID_CLASSES:
        return cls
    return _FALLBACK_CLASS


class KsiCompliancePanelType:
    """Panel type for the FedRAMP 20x KSI compliance reference view."""

    slug: ClassVar[str] = "fedramp-20x-ksi-compliance"
    label: ClassVar[str] = "FedRAMP 20x KSI Compliance View"
    view: ClassVar[str] = "fedramp_20x_ksi/panels/compliance_view.html"
    css: ClassVar[list[str]] = [
        "tap_web/css/lib/tabulator.min.css",
        "fedramp_20x_ksi/css/panel-ksi-compliance.css",
    ]
    js: ClassVar[list[str]] = [
        "tap_web/js/lib/tabulator.min.js",
        "fedramp_20x_ksi/js/panel-ksi-compliance.js",
    ]
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Execute the linked gryphon search and return the raw subgraph for JS.

        The subgraph envelope ({nodes, edges}) is passed directly to the browser
        via safe_json(). The JS handles joining indicators to themes via edges
        and building the grouped table.
        """
        from tap_web.panel import get_panel_search

        default_class = _resolve_default_class()

        search = get_panel_search(panel)
        if search is None:
            return {
                "ksi_subgraph_json": safe_json({"nodes": [], "edges": []}),
                "ksi_default_class_json": safe_json(default_class),
                "ksi_error": "No search linked to this panel.",
            }

        try:
            from tap_grid.search import execute_search

            result = execute_search(search, layer="extended")
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[d569] KSI compliance search execution failed for panel %s",
                panel.entity_id,
            )
            return {
                "ksi_subgraph_json": safe_json({"nodes": [], "edges": []}),
                "ksi_default_class_json": safe_json(default_class),
                "ksi_error": f"Search execution failed: {exc}",
            }

        if "results" in result:
            subgraph = result["results"]
        else:
            subgraph = result

        return {
            "ksi_subgraph_json": safe_json(subgraph),
            "ksi_default_class_json": safe_json(default_class),
            "ksi_error": None,
        }
