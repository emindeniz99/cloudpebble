# Adds the 'tsx' source target used by alloy projects whose embedded JS is
# compiled from TypeScript before the Moddable prebuild.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ide', '0013_github_hook_force'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sourcefile',
            name='target',
            field=models.CharField(
                choices=[
                    ('app', 'App'),
                    ('pkjs', 'PebbleKit JS'),
                    ('worker', 'Worker'),
                    ('public', 'Public Header File'),
                    ('common', 'Shared JS'),
                    ('embeddedjs', 'Embedded JS'),
                    ('tsx', 'TypeScript source'),
                    ('assets', 'Moddable asset'),
                ],
                default='app',
                max_length=12,
            ),
        ),
    ]
