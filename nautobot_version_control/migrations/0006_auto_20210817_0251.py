# Generated by Django 3.1.13 on 2021-08-17 02:51

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("nautobot_version_control", "0005_pullrequest_pullrequestreview"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pullrequest",
            name="creator",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="users.user"),
        ),
        migrations.AlterField(
            model_name="pullrequest",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="pullrequestreview",
            name="reviewer",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="users.user"),
        ),
        migrations.AlterField(
            model_name="pullrequestreview",
            name="summary",
            field=models.TextField(blank=True, null=True),
        ),
    ]
