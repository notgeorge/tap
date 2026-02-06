"""tap_viz models — Layout storage for Cytoscape.js visualizations."""

from django.db import models

from tap_core.models import BaseModel


class Layout(BaseModel):
    """A saved Cytoscape.js layout configuration.

    Layouts are Entities (via BaseModel). The cytoscape_config JSONField
    stores the full layout in Cytoscape-ingestible format: nodes, edges,
    positions, style, and layout algorithm settings.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    cytoscape_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full Cytoscape.js config: nodes, edges, positions, style.",
    )

    class Meta(BaseModel.Meta):
        db_table = "tap_layout"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name
