# Generated manually for icon_data field addition

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tap_core', '0002_entity_entitytype_edge'),
    ]

    operations = [
        migrations.AddField(
            model_name='entitytype',
            name='icon_data',
            field=models.JSONField(blank=True, default=dict, help_text='Structured icon data with type, value, and metadata. Preferred over icon CharField.'),
        ),
        migrations.AlterField(
            model_name='entitytype',
            name='icon',
            field=models.CharField(blank=True, default='', help_text="Icon reference. Format: 'type:value' (e.g., 'named:fa-server', 'static:plugin/icon.svg')", max_length=255),
        ),
    ]
