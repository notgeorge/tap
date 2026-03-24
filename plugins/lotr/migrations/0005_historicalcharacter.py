# Generated migration — adds HistoricalCharacter for django-simple-history (FLIP).

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models

import tap_grid.models


class Migration(migrations.Migration):

    dependencies = [
        ("lotr", "0004_remove_artifact_created_at_and_more"),
        ("tap_grid", "0009_rename_display_name_entity_name_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricalCharacter",
            fields=[
                ("id", models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name="ID")),
                (
                    "batch_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="UUIDv7 of the batch this change was included in (FLIP Phase 2).",
                        max_length=36,
                    ),
                ),
                ("bio", models.TextField(blank=True, default="")),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1
                    ),
                ),
                (
                    "entity",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tap_grid.entity",
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical character",
                "verbose_name_plural": "historical characters",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
