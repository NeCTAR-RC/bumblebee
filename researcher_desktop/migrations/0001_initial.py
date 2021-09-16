# Generated by Django 3.2.7 on 2021-09-15 03:55

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DesktopType',
            fields=[
                ('name', models.CharField(max_length=32, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, max_length=256)),
                ('image_name', models.CharField(max_length=256)),
                ('default_flavor_name', models.CharField(max_length=32)),
                ('big_flavor_name', models.CharField(max_length=32)),
                ('enabled', models.BooleanField(default=True)),
            ],
        ),
    ]