"""Domain models for the core examples plugin."""

from typing import Any, ClassVar

from django.db import models

from tap_core.models import BaseModel


class Concept(BaseModel):
    """An abstract idea or principle."""

    # Concepts can create APPLIES_TO edges to concepts and precepts
    # Concepts can create DEPENDS_ON edges to other concepts
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "concept"}, {"type": "precept"}],
            "edges": [{"type": "APPLIES_TO"}],
        },
        {
            "nodes": [{"type": "concept"}],
            "edges": [{"type": "DEPENDS_ON"}],
        },
    ]

    # Concepts can receive APPLIES_TO and DEPENDS_ON from other concepts
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "concept"}],
            "edges": [{"type": "APPLIES_TO"}, {"type": "DEPENDS_ON"}],
        },
    ]

    summary = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "core_examples_concept"

    def __str__(self) -> str:
        return self.entity.display_name


class Precept(BaseModel):
    """A rule or instruction derived from a concept."""

    # Precepts can create DEPENDS_ON edges to concepts
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "concept"}],
            "edges": [{"type": "DEPENDS_ON"}],
        },
    ]

    # Precepts can receive APPLIES_TO from concepts
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "concept"}],
            "edges": [{"type": "APPLIES_TO"}],
        },
    ]

    statement = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "core_examples_precept"

    def __str__(self) -> str:
        return self.entity.display_name
