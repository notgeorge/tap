"""Table Panel — built-in panel type for search-backed tabular display.

Stores all behavior options in the standard Panel.config JSONField,
validated against TABLE_CONFIG_SCHEMA on every save.

Search binding:
  Panel links to a Search via a USES_SEARCH edge (Panel -> Search).
  The linked Search is executed through the shared search service layer;
  no ORM or module search logic lives in this panel.

Rendering:
  Server-side: the linked Search executes during panel fragment rendering.
  Client-side: Tabulator 6.3 initializes from an embedded JSON payload.

Pagination:
  Server-backed. Limit/offset are passed as query params on the HTMX
  panel endpoint; Tabulator local pagination is not used.

Config schema:
  See req-web-stdpanel-table-config in spec-web-panels-standard-table.md.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from tap_web.utils import safe_json

import jsonschema  # type: ignore[import-untyped]
from django import forms
from django.core.exceptions import ValidationError

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_grid.models import Search
    from tap_web.models import Panel

logger = logging.getLogger(__name__)

# JSON Schema for Panel.config on Table Panel instances.
# additionalProperties: false enforces no undeclared keys.
TABLE_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "column_mode": {
            "type": "string",
            "enum": ["common_metadata"],
        },
        "default_limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
        },
    },
}

_DEFAULT_LIMIT = 25
_DEFAULT_COLUMN_MODE = "common_metadata"


def _validate_table_config(config: dict[str, Any]) -> None:
    """Validate a Table Panel config dict against TABLE_CONFIG_SCHEMA.

    Raises:
        ValidationError: if the config fails schema validation.
    """
    try:
        jsonschema.validate(instance=config, schema=TABLE_CONFIG_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ValidationError({"config": [exc.message]}) from exc


class TablePanelEditForm(forms.Form):
    """Edit form for Table Panel fields.

    Dynamically populates the search_uuid choices from available Search objects
    so the editor shows a human-readable dropdown rather than a raw UUID input.
    Server-side validation enforces required constraints independently of
    any browser-side checks.
    """

    name = forms.CharField(max_length=255, strip=True)
    description = forms.CharField(required=False, strip=True, widget=forms.Textarea)
    search_uuid = forms.ChoiceField(required=False, label="Linked Search")
    column_mode = forms.ChoiceField(
        choices=[("common_metadata", "Common Metadata")],
        initial=_DEFAULT_COLUMN_MODE,
        label="Column Mode",
    )
    default_limit = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=500,
        initial=_DEFAULT_LIMIT,
        label="Default Rows Per Page",
        help_text="Number of rows shown per page. Clamped to the linked Search's max_limit.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Populate search choices at form instantiation so they reflect current DB state.
        from tap_grid.models import Search

        choices = [("", "— No search linked —")]
        for s in Search.objects.select_related("entity").order_by("name"):
            choices.append((str(s.entity_id), s.name or str(s.entity_id)))
        self.fields["search_uuid"].choices = choices  # type: ignore[attr-defined]


class TablePanelType:
    """Built-in table panel type descriptor.

    Implements the three optional PanelType hooks used by panel_view and
    panel_edit_view:
      - get_view_context(panel, request) -> dict
      - get_editor_initial(panel) -> dict
      - handle_save(form, panel, request) -> None
    """

    slug = "table"
    label = "Table Panel"
    view = "tap_web/panels/table_panel.html"
    editor_view = "tap_web/panels/table_panel_editor.html"
    css: list[str] = ["css/lib/tabulator.min.css"]
    js: list[str] = ["js/lib/tabulator.min.js", "js/panel-table.js"]
    config_defaults: dict[str, Any] = {
        "column_mode": _DEFAULT_COLUMN_MODE,
        "default_limit": _DEFAULT_LIMIT,
    }
    form_class = TablePanelEditForm

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Execute the linked Search and return results for template context.

        Returns a context dict with:
          table_nodes      - list of node dicts from the search envelope
          table_meta       - pagination metadata dict (empty if unpaginated)
          table_search     - the linked Search instance, or None
          table_nodes_json - JSON-encoded nodes string for safe embedding
          table_error      - error string, or None on success
        """
        from tap_web.panel import get_panel_search

        search = get_panel_search(panel)
        if search is None:
            return {
                "table_nodes": [],
                "table_meta": {},
                "table_search": None,
                "table_nodes_json": safe_json([]),
                "table_error": "No search linked to this panel.",
            }

        config = panel.config or {}
        limit = _safe_int(request.GET.get("limit"), config.get("default_limit", _DEFAULT_LIMIT))
        offset = _safe_int(request.GET.get("offset"), 0)

        try:
            from tap_grid.search import execute_search

            result = execute_search(search, limit=limit, offset=offset, layer="extended")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Table panel search execution failed for panel %s", panel.entity_id)
            return {
                "table_nodes": [],
                "table_meta": {},
                "table_search": search,
                "table_nodes_json": safe_json([]),
                "table_error": f"Search execution failed: {exc}",
            }

        # Paginated envelope: {"count", "limit", "offset", "results": envelope}
        if "results" in result:
            nodes: list[dict[str, Any]] = result["results"].get("nodes", [])
            effective_limit: int = result["limit"]
            effective_offset: int = result["offset"]
            count: int = result["count"]
            meta: dict[str, Any] = {
                "count": count,
                "limit": effective_limit,
                "offset": effective_offset,
                "has_prev": effective_offset > 0,
                "has_next": effective_offset + effective_limit < count,
                "prev_offset": max(0, effective_offset - effective_limit),
                "next_offset": effective_offset + effective_limit,
                "display_end": min(effective_offset + effective_limit, count),
            }
        else:
            nodes = result.get("nodes", [])
            meta = {}

        return {
            "table_nodes": nodes,
            "table_meta": meta,
            "table_search": search,
            "table_nodes_json": safe_json(nodes),
            "table_error": None,
        }

    @classmethod
    def get_editor_initial(cls, panel: Panel) -> dict[str, Any]:
        """Return the initial dict for TablePanelEditForm.

        Includes the currently linked search UUID so the editor dropdown
        pre-selects the right Search.
        """
        from tap_web.panel import get_panel_search

        search: Search | None = get_panel_search(panel)
        config = panel.config or {}
        return {
            "name": panel.name,
            "description": panel.description,
            "search_uuid": str(search.entity_id) if search else "",
            "column_mode": config.get("column_mode", _DEFAULT_COLUMN_MODE),
            "default_limit": config.get("default_limit", _DEFAULT_LIMIT),
        }

    @classmethod
    def handle_save(cls, form: TablePanelEditForm, panel: Panel, request: HttpRequest) -> None:
        """Persist panel fields, validate config, and update the USES_SEARCH edge.

        Steps:
          1. Apply title and description to the panel instance.
          2. Build and validate the config dict against TABLE_CONFIG_SCHEMA.
          3. Save the panel.
          4. Replace the USES_SEARCH edge binding (delete old, create new).

        Raises:
            ValidationError: if the config fails schema validation.
        """
        from tap_grid.models import Edge, Entity

        cleaned = form.cleaned_data

        panel.name = cleaned["name"]
        panel.description = cleaned.get("description", "")

        new_config: dict[str, Any] = {
            "column_mode": cleaned.get("column_mode") or _DEFAULT_COLUMN_MODE,
            "default_limit": cleaned.get("default_limit") or _DEFAULT_LIMIT,
        }
        _validate_table_config(new_config)
        panel.config = new_config
        panel.save()

        # Replace the USES_SEARCH edge.
        Edge.objects.filter(from_entity=panel.entity, edge_type="USES_SEARCH").delete()

        search_uuid_str: str = cleaned.get("search_uuid") or ""
        if search_uuid_str:
            try:
                search_entity = Entity.objects.get(pk=search_uuid_str)
                Edge.objects.create(
                    from_entity=panel.entity,
                    to_entity=search_entity,
                    edge_type="USES_SEARCH",
                )
            except Entity.DoesNotExist:
                logger.warning(
                    "Table panel editor: search entity %s not found; USES_SEARCH edge not created.",
                    search_uuid_str,
                )




def _safe_int(value: Any, default: int) -> int:
    """Return int(value) if convertible and positive, otherwise default."""
    try:
        result = int(value)
        return result if result > 0 else default
    except TypeError, ValueError:
        return default
