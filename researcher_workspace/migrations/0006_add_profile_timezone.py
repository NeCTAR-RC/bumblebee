# Generated by Django 3.2.7 on 2021-12-06 04:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('researcher_workspace', '0005_add_chief_investigator'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='timezone',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
