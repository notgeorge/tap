"""TAP Web models — Page, Panel, LandingPage.

All tap_web node types declare DEFAULT_DIMENSIONS = {"tap.graph": "web"}
to keep web artifacts in their own named partition of the graph.
"""

from typing import Any, ClassVar

from django.apps import apps
from django.db import models

from tap_grid.models import BaseModel
from tap_web.validation import validate_page_layout, validate_page_slug, validate_panel_assets


class Page(BaseModel):
    """A routable web page that hosts one or more panels."""

    ENTITY_TYPE: ClassVar[str] = "page"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.graph": "web"}

    # Hotlink contract: panel-id values embedded in layout must exactly match
    # the hotlink.value on the page's outbound USES_PANEL edges.
    HOTLINKS: ClassVar[list[dict]] = [
        {
            "name": "page-panels",
            "field": "layout",
            "selector_type": "simple_path",
            "selector": "columns.*.rows.*.panel-id",
            "edge_direction": "outbound",
            "edge_type": "USES_PANEL",
            "mode": "exact",
        }
    ]

    name = models.CharField(max_length=255)
    slug = models.CharField(
        max_length=255,
        unique=True,
        help_text="Route path starting with /. Example: /my-page",
    )
    description = models.TextField(blank=True, default="")
    layout = models.JSONField(
        default=dict,
        help_text="Nested grid layout schema (columns → rows → panel-id slots).",
    )

    class Meta(BaseModel.Meta):
        db_table = "web_page"

    def save(self, *args: Any, **kwargs: Any) -> None:
        reserved = _get_reserved_slugs()
        validate_page_slug(self.slug, reserved_prefixes=reserved)
        validate_page_layout(self.layout or {})
        super().save(*args, **kwargs)

    def get_name(self) -> str:
        return self.name or ""

    def __str__(self) -> str:
        return self.name or self.slug or ""


class Panel(BaseModel):
    """A data-display component embedded in a Page.

    Each Panel declares a template path (`view`), optional static assets
    (`js`, `css`), and a human-readable `slug` used in its HTMX URL.
    The HTMX endpoint is /panel/<slug>--<entity-uuid>/.
    """

    ENTITY_TYPE: ClassVar[str] = "panel"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.graph": "web"}

    slug = models.CharField(
        max_length=255,
        help_text="Kebab-case label used in the HTMX URL alongside the entity UUID. Not globally unique.",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    view = models.CharField(
        max_length=500,
        help_text="Template path rendered by the generic panel view. Example: tap_plugins/lotr/templates/character_list.html",
    )
    editor_view = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Template path for the panel editor UI. Optional; only set when the panel supports edit mode.",
    )
    config = models.JSONField(
        default=dict,
        help_text="Panel-specific configuration object. Default: {}.",
    )
    js = models.JSONField(
        default=list,
        help_text="Flat list of static-relative JS paths. Example: ['js/cytoscape.js']",
    )
    css = models.JSONField(
        default=list,
        help_text="Flat list of static-relative CSS paths. Example: ['css/panel.css']",
    )
    editor_js = models.JSONField(
        default=list,
        help_text="Flat list of static-relative JS paths used in panel edit mode. Default: [].",
    )
    editor_css = models.JSONField(
        default=list,
        help_text="Flat list of static-relative CSS paths used in panel edit mode. Default: [].",
    )
    input_vars = models.JSONField(
        default=list,
        help_text="Declared panel input variable names expected at runtime. Default: [].",
    )

    class Meta(BaseModel.Meta):
        db_table = "web_panel"

    def save(self, *args: Any, **kwargs: Any) -> None:
        validate_panel_assets(self)
        super().save(*args, **kwargs)

    def get_name(self) -> str:
        return self.name or ""

    def __str__(self) -> str:
        return self.name or self.slug or ""


class LandingPage(BaseModel):
    """Indirection node that designates which Page is served at the root URL.

    The earliest-created LandingPage (by entity__created_at) is used when
    multiple LandingPage nodes exist.
    """

    ENTITY_TYPE: ClassVar[str] = "landing_page"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.graph": "web"}

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "web_landing_page"

    def get_name(self) -> str:
        return self.name or ""

    def __str__(self) -> str:
        return self.name or "LandingPage"


def _get_reserved_slugs() -> list[str]:
    """Return the reserved slug prefixes from TapWebConfig."""
    try:
        config = apps.get_app_config("tap_web")
        return list(getattr(config, "reserved_slugs", []))
    except Exception:  # noqa: BLE001
        return []
