# Generated by Django 3.2.12 on 2022-04-20 08:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vm_manager', '0011_expires_cleanup'),
    ]

    operations = [
        migrations.AddField(
            model_name='vmstatus',
            name='status_done',
            field=models.TextField(blank=True, null=True),
        ),
    ]