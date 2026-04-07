from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tap_grid", "0016_entity_version"),
    ]

    operations = [
        migrations.RenameField(
            model_name="batch",
            old_name="title",
            new_name="name",
        ),
        migrations.RenameField(
            model_name="historicalbatch",
            old_name="title",
            new_name="name",
        ),
    ]
