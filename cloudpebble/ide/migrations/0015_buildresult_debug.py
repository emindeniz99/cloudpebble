# Records whether a build was a debug build (faster, keeps source maps) or a
# release one (the artifact you would publish).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ide', '0014_sourcefile_tsx_target'),
    ]

    operations = [
        migrations.AddField(
            model_name='buildresult',
            name='debug',
            field=models.BooleanField(default=False),
        ),
    ]
