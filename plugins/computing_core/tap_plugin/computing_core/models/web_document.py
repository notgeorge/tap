"""Web Document — a document retrievable at a URL over HTTP(S)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class WebDocument(BaseModel):
    """A document retrievable at a URL over HTTP(S).

    Distinct from ``file`` (a filesystem object keyed by path): a web document
    is network-delivered content addressed by URL, e.g. the CISA KEV catalog.
    Carries the ``tap.web`` dimension marker so a future ``web_core`` split can
    lift every web-native type in one shot.

    Spec: plugins/computing_core/specs/spec-computing-core-v0.md
    """

    ENTITY_TYPE: ClassVar[str] = "computing_core__web_document"
    ENTITY_NAME: ClassVar[str] = "Web Document"
    ENTITY_DESCRIPTION: ClassVar[str] = "A document retrievable at a URL over HTTP(S)."
    ENTITY_ICON: ClassVar[str] = "web-document"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "storage", "tap.web": "native"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#5EA8B2", "border": "#2B7E83", "label": "#FFFFFF"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "url": {"type": "string", "minLength": 1},
        "content_type": {"type": "string"},
        "version": {"type": "string"},
        "retrieved_at": {"type": ["string", "null"]},
        "description": {"type": "string"},
    }

    # FIELD_VALIDATION_SCHEMA runs on save with the post-parse Python value.
    # retrieved_at is a Django DateTimeField — its own validation is the right
    # layer, so it is intentionally omitted here. The CRUD "string | null"
    # entry above describes only the inbound JSON shape, not the at-rest value.
    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "url": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "content_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "version": {"validation": "jsonschema", "schema": {"type": "string"}},
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["url"]

    name = models.CharField(max_length=255, blank=True, default="")
    url = models.CharField(max_length=2048, blank=True, default="", db_index=True)
    content_type = models.CharField(max_length=128, blank=True, default="")
    version = models.CharField(max_length=128, blank=True, default="")
    retrieved_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "computing_core__web_document"

    def get_name(self) -> str:
        return self.name or self.url

    def __str__(self) -> str:
        return self.get_name()
