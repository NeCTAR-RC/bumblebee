# Generated by Django 3.2.9 on 2022-02-08 01:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vm_manager', '0007_remove_shelved'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cloudresource',
            name='error_message',
            field=models.TextField(blank=True, null=True),
        ),
    ]
