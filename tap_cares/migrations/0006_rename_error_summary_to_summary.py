from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tap_cares", "0005_alter_collectionjob_grift_batches_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="collectionjob",
            old_name="error_summary",
            new_name="summary",
        ),
        migrations.RenameField(
            model_name="historicalcollectionjob",
            old_name="error_summary",
            new_name="summary",
        ),
    ]
