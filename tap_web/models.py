"""TAP Web models — Page, Panel, LandingPage.

All tap_web node types declare DEFAULT_DIMENSIONS = {"tap.graph": "web"}
to keep web artifacts in their own named partition of the graph.
"""

from typing import ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Page(BaseModel):
    """A routable web page that hosts one or more panels."""

    ENTITY_TYPE: ClassVar[str] = "page"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.graph": "web"}

    title = models.CharField(max_length=255)
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

    def get_display_name(self) -> str:
        return self.title or ""

    def __str__(self) -> str:
        return self.title or self.slug or ""


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
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    view = models.CharField(
        max_length=500,
        help_text="Template path rendered by the generic panel view. Example: tap_plugins/lotr/templates/character_list.html",
    )
    js = models.JSONField(
        default=list,
        help_text="Flat list of static-relative JS paths. Example: ['js/cytoscape.js']",
    )
    css = models.JSONField(
        default=list,
        help_text="Flat list of static-relative CSS paths. Example: ['css/panel.css']",
    )

    class Meta(BaseModel.Meta):
        db_table = "web_panel"

    def get_display_name(self) -> str:
        return self.title or ""

    def __str__(self) -> str:
        return self.title or self.slug or ""


class LandingPage(BaseModel):
    """Indirection node that designates which Page is served at the root URL.

    The earliest-created LandingPage (by entity__created_at) is used when
    multiple LandingPage nodes exist.
    """

    ENTITY_TYPE: ClassVar[str] = "landing_page"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.graph": "web"}

    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "web_landing_page"

    def get_display_name(self) -> str:
        return self.title or ""

    def __str__(self) -> str:
        return self.title or "LandingPage"
