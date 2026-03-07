# Generated manually — adds fields to Page, Panel, LandingPage.
# Dev tables only had stub rows; existing rows are cleared before adding
# required non-nullable fields to avoid one-off default complexity.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tap_web", "0001_initial"),
    ]

    operations = [
        # Clear stub rows so required fields can be added without defaults.
        # These tables only hold test/seed data at this stage.
        migrations.RunSQL(
            sql="DELETE FROM web_page; DELETE FROM web_panel; DELETE FROM web_landing_page;",
            reverse_sql=migrations.RunSQL.noop,
        ),

        # --- Page fields ---
        migrations.AddField(
            model_name="page",
            name="title",
            field=models.CharField(max_length=255),
        ),
        migrations.AddField(
            model_name="page",
            name="slug",
            field=models.CharField(
                max_length=255,
                unique=True,
                help_text="Route path starting with /. Example: /my-page",
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="page",
            name="layout",
            field=models.JSONField(
                default=dict,
                help_text="Nested grid layout schema (columns → rows → panel-id slots).",
            ),
        ),

        # --- Panel fields ---
        migrations.AddField(
            model_name="panel",
            name="slug",
            field=models.CharField(
                max_length=255,
                help_text="Kebab-case label used in the HTMX URL alongside the entity UUID. Not globally unique.",
            ),
        ),
        migrations.AddField(
            model_name="panel",
            name="title",
            field=models.CharField(max_length=255),
        ),
        migrations.AddField(
            model_name="panel",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="panel",
            name="view",
            field=models.CharField(
                max_length=500,
                help_text="Template path rendered by the generic panel view.",
            ),
        ),
        migrations.AddField(
            model_name="panel",
            name="js",
            field=models.JSONField(
                default=list,
                help_text="Flat list of static-relative JS paths.",
            ),
        ),
        migrations.AddField(
            model_name="panel",
            name="css",
            field=models.JSONField(
                default=list,
                help_text="Flat list of static-relative CSS paths.",
            ),
        ),

        # --- LandingPage fields ---
        migrations.AddField(
            model_name="landingpage",
            name="title",
            field=models.CharField(max_length=255, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="landingpage",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
    ]
