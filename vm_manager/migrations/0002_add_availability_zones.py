# Generated by Django 3.2.7 on 2021-10-20 11:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vm_manager', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='volume',
            name='zone',
            field=models.CharField(max_length=32, null=True),
        ),
    ]
