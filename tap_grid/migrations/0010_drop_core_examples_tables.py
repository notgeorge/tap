# Drops orphaned core_examples tables after plugin removal.
# Also cleans django_migrations rows for the removed app.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tap_grid", "0009_rename_display_name_entity_name_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DROP TABLE IF EXISTS "core_examples_historicalconcept";
                DROP TABLE IF EXISTS "core_examples_concept";
                DROP TABLE IF EXISTS "core_examples_precept";
                DELETE FROM django_migrations WHERE app = 'core_examples';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
