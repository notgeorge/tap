"""Domain models for the test plugin."""

from django.db import models

from tap_core.models import BaseModel


class Concept(BaseModel):
    """An abstract idea or principle."""

    summary = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "test_plugin_concept"

    def __str__(self) -> str:
        return self.entity.display_name


class Precept(BaseModel):
    """A rule or instruction derived from a concept."""

    statement = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "test_plugin_precept"

    def __str__(self) -> str:
        return self.entity.display_name
