# Generated by Django 3.2.9 on 2022-02-11 03:30

from django.db import migrations
from researcher_workspace.models import Char32UUIDField


class Migration(migrations.Migration):

    dependencies = [
        ('researcher_workspace', '0007_alter_permission_project'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='sub',
            field=Char32UUIDField(null=True, unique=True),
            preserve_default=False,
        ),
    ]
