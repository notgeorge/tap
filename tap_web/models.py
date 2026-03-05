"""TAP Web models — Page, Panel, LandingPage.

All tap_web node types declare DEFAULT_DIMENSIONS = {"tap.graph": "web"}
to keep web artifacts in their own named partition of the graph.

Fields beyond what's declared here are added in subsequent requirements
(req-web-page-obj, req-web-page-plink, req-web-page-landing).
"""

from typing import ClassVar

from tap_grid.models import BaseModel


class Page(BaseModel):
    """A routable web page that hosts one or more panels."""

    ENTITY_TYPE: ClassVar[str] = "page"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.graph": "web"}

    class Meta(BaseModel.Meta):
        db_table = "web_page"

    def __str__(self) -> str:
        return self.entity.display_name


class Panel(BaseModel):
    """A data-display component embedded in a Page.

    Stub — fields added in the Panel spec.
    """

    ENTITY_TYPE: ClassVar[str] = "panel"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.graph": "web"}

    class Meta(BaseModel.Meta):
        db_table = "web_panel"

    def __str__(self) -> str:
        return self.entity.display_name


class LandingPage(BaseModel):
    """Indirection node that designates which Page is served at the root URL."""

    ENTITY_TYPE: ClassVar[str] = "landing_page"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.graph": "web"}

    class Meta(BaseModel.Meta):
        db_table = "web_landing_page"

    def __str__(self) -> str:
        return self.entity.display_name
