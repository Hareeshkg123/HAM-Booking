from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_profile_is_host'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='host_requested',
            field=models.BooleanField(default=False),
        ),
    ]
