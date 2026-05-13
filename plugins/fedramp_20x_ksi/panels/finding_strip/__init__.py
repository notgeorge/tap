"""Finding Strip Panel — horizontal strip of compliance-finding tiles.

Renders one tile per entry in panel.config["tiles"]. Each tile runs a
gryphon query at request time and shows a single integer drawn from the
named field of the first returned row (or summed across rows when
mode="sum").

Tile schema (per tile):
  label        - tile heading (uppercase small caps in v0)
  color        - accent dot color (CSS color string)
  query        - gryphon query as a list of strings, joined with newlines
  value_field  - row alias to read the value from (default "value")
  mode         - "first" (default; read field from rows[0]) or "sum"
                 (sum value_field across all returned rows)
  hint         - optional secondary line under the label

Display-only in v0; click-through is a follow-on. See
spec-fedramp-20x-ksi-finding-strip.md for the full contract.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


class FindingStripPanelType:
    slug = "finding_strip"
    label = "Finding Strip"
    view = "fedramp_20x_ksi/panels/finding_strip.html"
    css: list[str] = ["fedramp_20x_ksi/css/finding_strip.css"]
    config_defaults: dict[str, Any] = {"tiles": []}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        from tap_grid.gryphon.executor import execute_gryphon_raw

        tiles_cfg = (panel.config or {}).get("tiles") or []
        rendered: list[dict[str, Any]] = []

        for tile in tiles_cfg:
            label = tile.get("label", "")
            color = tile.get("color", "#64748b")
            value_field = tile.get("value_field", "value")
            mode = tile.get("mode", "first")
            hint = tile.get("hint", "")
            raw_query = tile.get("query", "")
            query = "\n".join(raw_query) if isinstance(raw_query, list) else raw_query

            value: Any = None
            error: str | None = None
            try:
                envelope = execute_gryphon_raw(query, {}, db_alias="search_readonly")
                rows = envelope.get("rows") or []
                if mode == "sum":
                    value = sum((row.get(value_field) or 0) for row in rows)
                elif rows:
                    value = rows[0].get(value_field)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Finding Strip tile '%s' query failed", label)
                error = str(exc)

            rendered.append(
                {
                    "label": label,
                    "color": color,
                    "value": value if value is not None else 0,
                    "hint": hint,
                    "error": error,
                }
            )

        return {"finding_strip_tiles": rendered}
